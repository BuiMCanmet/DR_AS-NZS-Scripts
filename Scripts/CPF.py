"""
Copyright (c) 2018, Sandia National Labs, SunSpec Alliance and CanmetENERGY(Natural Resources Canada)
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this
list of conditions and the following disclaimer.

Redistributions in binary form must reproduce the above copyright notice, this
list of conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.

Neither the names of the Sandia National Labs, SunSpec Alliance and CanmetENERGY(Natural Resources Canada)
nor the names of its contributors may be used to endorse or promote products derived from
this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

Questions can be directed to support@sunspec.org
"""

import sys
import os
import traceback
from svpelab import gridsim
from svpelab import loadsim
from svpelab import pvsim
from svpelab import das
from svpelab import der
from svpelab import hil
from svpelab import pAus4777
import script
from svpelab import result as rslt
from datetime import datetime, timedelta

import numpy as np
import collections
import cmath
import math

CPF = 'CPF'
V = 'V'
F = 'F'
P = 'P'
Q = 'Q'


# Test protocol including constant power factor (and maybe reactive power)
def cpf_mode(mode=None):

    result = script.RESULT_FAIL
    daq = None
    v_nom = None
    grid = None
    pv = None
    eut = None
    chil = None
    result_summary = None
    dataset_filename = None

    try:
        # Rated powers
        p_rated = ts.param_value('eut.p_rated')
        var_rated = ts.param_value('eut.var_rated')
        s_rated = ts.param_value('eut.s_rated')

        # DC power
        if ts.param_value('pvsim.terrasas.pmp') is not None: # TODO - REPLACE WITH CORRECT REFERENCE
            p_pvsim = ts.param_value('pvsim.terrasas.pmp')
        else:
            p_pvsim = p_rated

        # DC voltages
        v_in_nom = ts.param_value('eut.v_in_nom')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_low = ts.param_value('eut.v_low')
        v_high = ts.param_value('eut.v_high')
        phases = ts.param_value('eut.phases')

        cpr_response_time = 0
        cpf_timing = [ts.param_value('cpf.commencement_time'),  # TODO - Fix these names
                     ts.param_value('cpf.completion_time'),
                     ts.param_value('cpf.step_time_period')]

        """
        A separate module has been create for the DR_AS_NZS_4777.2 Standard
        """
        pAus4777.VersionValidation(script_version=ts.info.version)
        Active_function = pAus4777.ActiveFunction(ts=ts, functions=[CPF])
        #ts.log_debug(f"AUS4777,2 Library configured for {Active_function.script_complete_name}")
        #ts.log_debug(f"AUS4777,2 Library configured for {Active_function.VoltWatt.get_params()}")

        # result params
        x_axis_specs = {'min': v_low * 0.9}
        #result_params = VoltWatt.get_rslt_param_plot(x_axis_specs=x_axis_specs)
        result_params = Active_function.get_rslt_param_plot(x_axis_specs=x_axis_specs)

        ts.log_debug(result_params)

        '''
        Connect the EUT according to the instructions and specifications provided by the manufacturer 
        and initialisation of the chil, pvsim, das, eut/der and the gridsim
        '''

        # initialize HIL environment, if necessary
        chil = hil.hil_init(ts)
        if chil is not None:
            chil.config()

        # initialize the pvsim
        pv = pvsim.pvsim_init(ts)

        # DAS soft channels
        das_points = Active_function.get_sc_points()
        # initialize data acquisition system
        daq = das.das_init(ts, sc_points=das_points['sc'])

        daq.sc['V_TARGET'] = v_nom
        daq.sc['TR_SS_TARGET'] = 10
        daq.sc['Q_TARGET'] = 100
        daq.sc['Q_TARGET_MIN'] = 100
        daq.sc['Q_TARGET_MAX'] = 100
        daq.sc['P_TARGET'] = 100
        daq.sc['P_TARGET_MIN'] = 100
        daq.sc['P_TARGET_MAX'] = 100
        daq.sc['event'] = 'None'

        ts.log(f'DAS device: {daq.info()}')

        # Setting the pvsim to the rated power of the eut
        if pv is not None:
            pv.iv_curve_config(pmp=p_pvsim, vmp=v_in_nom)
            pv.irradiance_set(1000.)
            pv.power_on()  # Turn on DC so the EUT can be initialized
            pvsim_sleeptime = 30
            ts.log(f"PV simulator enabled, sleeping for {pvsim_sleeptime} seconds to allow EUT to stabilise")
            ts.sleep(pvsim_sleeptime)

        # initialize the eut
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            # ts.log_debug(eut.measurements())

            #Deactivating all functions on EUT
            #eut.deactivate_all_fct()

        # initialize the GridSim
        grid = gridsim.gridsim_init(ts, support_interfaces={'hil': chil})  # Turn on AC so the EUT can be initialized
        if grid is not None:
            gridsim_sleeptime = 90
            ts.log(f"Grid simulator enabled, sleeping for {gridsim_sleeptime} seconds to allow EUT to connect")
            ts.sleep(gridsim_sleeptime)

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        ts.log(f'col_name={Active_function.get_rslt_sum_col_name()}')
        result_summary.write(Active_function.get_rslt_sum_col_name())

        Active_function.reset_time_settings(tr=cpf_timing, number_tr=3)

        cpf_settings = Active_function.get_params(function=CPF, region=None)
        ts.log_debug(f'cpf-settings:{cpf_settings}')

        '''
        (a) Enable the constant power factor mode.
        '''

        if eut is not None: # TODO - Need to add a changing PF to the test proper. Possibly move this entirely?
            # Activate constant power factor function with following parameters
            cpf_setting_params = {'PF': cpf_settings['PF']['PF1']}
            #ts.log_debug(f'cpf_setting_params:{cpf_setting_params}')
            ts.log_debug(f'Sending PF settings: {cpf_setting_params}')
            eut.fixed_pf(params={'Ena': True, 'PF': cpf_setting_params['PF']})  # TODO - this doesn't look right at all. Doesn't this need a dict {'PF': pf}?
            ts.log_debug(f'PF settings sent: {cpf_setting_params}, now retrieving set data.')
            ts.log_debug(f'Initial EUT PF settings are {eut.fixed_pf()}')
        """
         (b) Set the grid source equal to the grid test voltage. Vary the energy source until the a.c. output
            of the device under test equals 100 ± 5 % of its rated active power output.
        """
        # Setting grid to vnom before test
        if grid is not None:
            grid.voltage(v_nom)
        # Setting the pvsim to the rated power of the eut
        if pv is not None:
            pv.iv_curve_config(pmp=p_pvsim, vmp=v_in_nom)
            #pv.iv_curve_config(pmp=p_rated, vmp=v_in_nom)
            pv.irradiance_set(1000.)

        """
        Going through test steps
        """

        p_pf_steps_dict = Active_function.create_cpf_dict_steps()

        dataset_filename = 'CPF'
        Active_function.reset_filename(filename=dataset_filename)
        # Start the data acquisition systems
        daq.data_capture(True)

        prev_pf_target = -9999

        for step_label, p_pf_step in p_pf_steps_dict.items():
            ts.log_debug(step_label)
            ts.log_debug(p_pf_step)
        #for pf_key, pf_setting in cpf_settings['PF'].items():
            if eut is not None:
                # Activate constant power factor function with following parameters
                pf_setting = p_pf_step['PF']
                if pf_setting != prev_pf_target:
                    # cpf_setting_params = {'PF': [pf_setting]}
                    ts.log_debug(f'Sending PF settings: {pf_setting}')
                    eut.fixed_pf(params={'Ena': True, 'PF': pf_setting})
                    ts.log_debug(f'EUT PF settings are {eut.fixed_pf()}')
                    prev_pf_target = pf_setting

            # for p_key, p_setting in cpf_settings['P'].items():
            p_setting = p_pf_step['P']
            if pv is not None:
                #ts.log_debug(f'Sending power setting: {p_setting}')
                pv.power_set(p_setting)

            Active_function.start(daq=daq, step_label=step_label)
            #Active_function.start(daq=daq, step_label='X') # TODO - What to do about step_label?

            Active_function.record_timeresponse(daq=daq, step_value=min(p_setting, p_rated*abs(pf_setting)),
                                                y_target=pf_setting)
            Active_function.evaluate_criterias()
            result_summary.write(Active_function.write_rslt_sum())

        """
        (o) Summarize results in a table from initial value to final voltage value showing voltage,
            apparent power, active power, reactive power and time to reach required reactive power level
            for each voltage step. Plot results on a graph of voltage versus apparent power, active power
            and reactive power.
        """

        ts.log('Sampling complete')
        dataset_filename = dataset_filename + ".csv"
        daq.data_capture(False)
        ds = daq.data_capture_dataset()
        ts.log(f'Saving file: {dataset_filename}')
        ds.to_csv(ts.result_file_path(dataset_filename))
        result_params['plot.title'] = dataset_filename.split('.csv')[0]
        ts.result_file(dataset_filename, params=result_params)
        result = script.RESULT_COMPLETE

    except script.ScriptFail as e:
        reason = str(e)
        if reason:
            ts.log_error(reason)

    except Exception as e:
        if dataset_filename is not None:
            dataset_filename = dataset_filename + ".csv"
            daq.data_capture(False)
            ds = daq.data_capture_dataset()
            ts.log(f'Saving file: {dataset_filename}')
            ds.to_csv(ts.result_file_path(dataset_filename))
            result_params['plot.title'] = dataset_filename.split('.csv')[0]
            ts.result_file(dataset_filename, params=result_params)
        ts.log_error(f'Test script exception: {traceback.format_exc()}')


    finally:
        if daq is not None:
            daq.close()
        if pv is not None:
            pv.close()
        if grid is not None:
            if v_nom is not None:
                grid.voltage(v_nom)
            grid.close()
        if chil is not None:
            chil.close()
        if eut is not None:
            eut.close()
        if result_summary is not None:
            result_summary.close()

    return result

def test_run():

    result = script.RESULT_FAIL

    try:

        v_nom = ts.param_value('eut.v_nom')

        result = cpf_mode(mode=None)

    except script.ScriptFail as e:
        reason = str(e)
        if reason:
            ts.log_error(reason)

    finally:
        # create result workbook
        excelfile = ts.config_name() + '.xlsx'
        rslt.result_workbook(excelfile, ts.results_dir(), ts.result_dir())
        ts.result_file(excelfile)

    return result


def run(test_script):
    try:
        global ts
        ts = test_script
        rc = 0
        result = script.RESULT_COMPLETE

        ts.log_debug('')
        ts.log_debug(f'**************  Starting {ts.config_name()}  **************')
        ts.log_debug(f'Script: {ts.name} {ts.info.version}')
        ts.log_active_params()

        # ts.svp_version(required='1.5.3')
        ts.svp_version(required='1.5.8')

        result = test_run()
        ts.result(result)
        if result == script.RESULT_FAIL:
            rc = 1

    except Exception as e:
        ts.log_error(f'Test script exception: {traceback.format_exc()}')
        rc = 1

    sys.exit(rc)


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.1')

# cpf test parameters
info.param_group('cpf', label='Test Parameters')
info.param('cpf.commencement_time', label='Commencement time(s):', default=1.2)
info.param('cpf.completion_time', label='Completion time(s):', default=10.2)
info.param('cpf.step_time_period', label='Step time period(s):', default=20.0)

# EUT general parameters
info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.phases', label='Phases', default='Single Phase', values=['Single phase', 'Split phase', 'Three phase'])
info.param('eut.s_rated', label='Apparent power rating (VA)', default=10000.0)
info.param('eut.p_rated', label='Output power rating (W)', default=8000.0)
info.param('eut.p_min', label='Minimum Power Rating(W)', default=1000.)
info.param('eut.var_rated', label='Output var rating (vars)', default=2000.0)
info.param('eut.v_nom', label='Nominal AC voltage (V)', default=230.0, desc='Nominal voltage for the AC simulator.')
info.param('eut.v_low', label='Minimum AC voltage (V)', default=210.0)
info.param('eut.v_high', label='Maximum AC voltage (V)', default=250.0)
info.param('eut.v_in_nom', label='V_in_nom: Nominal input voltage (Vdc)', default=400)
info.param('eut.f_nom', label='Nominal AC frequency (Hz)', default=50.0)
info.param('eut.f_max', label='Maximum frequency in the continuous operating region (Hz)', default=55.)
info.param('eut.f_min', label='Minimum frequency in the continuous operating region (Hz)', default=45.)

'''
info.param('eut.imbalance_resp', label='EUT response to phase imbalance is calculated by:',
           default='EUT response to the average of the three-phase effective (RMS)',
           values=['EUT response to the individual phase voltages',
                   'EUT response to the average of the three-phase effective (RMS)',
                   'EUT response to the positive sequence of voltages'])
'''


# Other equipment parameters
der.params(info)
gridsim.params(info)
pvsim.params(info)
das.params(info)
hil.params(info)

# Add the SIRFN logo
info.logo('sirfn.png')

def script_info():
    return info


if __name__ == "__main__":

    # stand alone invocation
    config_file = None
    if len(sys.argv) > 1:
        config_file = sys.argv[1]

    params = None

    test_script = script.Script(info=script_info(), config_file=config_file, params=params)
    test_script.log('log it')

    run(test_script)
