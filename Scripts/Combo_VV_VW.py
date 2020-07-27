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
from svpelab import p1547
import script
from svpelab import result as rslt
from datetime import datetime, timedelta

import numpy as np
import collections
import cmath
import math

VV = 'VV'
VW = 'VW'
V = 'V'
F = 'F'
P = 'P'
Q = 'Q'

def Combo_vv_vw_mode(combo_vv_vw_curves, combo_vv_vw_response_time):

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

        # DC voltages
        v_in_nom = ts.param_value('eut.v_in_nom')

        # AC voltages
        v_nom = ts.param_value('eut.v_nom')
        v_low = ts.param_value('eut.v_low')
        v_high = ts.param_value('eut.v_high')
        phases = ts.param_value('eut.phases')

        """
        A separate module has been create for the 1547.1 and the DR_AS_NZS_4777.2 Standard
        """
        Combo_VoltVar_VoltWatt = p1547.VoltVar(ts=ts, imbalance=False)
        ts.log_debug(f"1547.1 Library configured for {Combo_VoltVar_VoltWatt.get_script_name()}")

        # result params
        result_params = Combo_VoltVar_VoltWatt.get_rslt_param_plot()
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
        #das_points = {'sc': ('Q_TARGET', 'Q_TARGET_MIN', 'Q_TARGET_MAX', 'Q_MEAS', 'V_TARGET', 'V_MEAS', 'event')}
        das_points = Combo_VoltVar_VoltWatt.get_sc_points()
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

        # initialize the eut
        eut = der.der_init(ts)
        if eut is not None:
            eut.config()
            ts.log_debug(eut.measurements())

            #Deactivating all functions on EUT
            eut.deactivate_all_fct()

        # initialize the GridSim
        grid = gridsim.gridsim_init(ts, support_interfaces={'hil': chil})  # Turn on AC so the EUT can be initialized

        # open result summary file
        result_summary_filename = 'result_summary.csv'
        result_summary = open(ts.result_file_path(result_summary_filename), 'a+')
        ts.result_file(result_summary_filename)
        result_summary.write(Combo_VoltVar_VoltWatt.get_rslt_sum_col_name())

        '''
        Repeat the test for each regions curves (Australia A, Australia B, Australia C, New Zealand and Allowed range)
        '''
        for combo_vv_vw_curve in combo_vv_vw_curves:
            ts.log(f'Starting test with characteristic curve {combo_vv_vw_curve}')
            Combo_VoltVar_VoltWatt.reset_curve(combo_vv_vw_curve)
            Combo_VoltVar_VoltWatt.reset_time_settings(tr=combo_vv_vw_response_time[combo_vv_vw_curve], number_tr=2)
            v_pairs = Combo_VoltVar_VoltWatt.get_params(curve=combo_vv_vw_curve)
            ts.log_debug(f'v_pairs:{v_pairs}')

            '''
            (a) Enable the volt-watt and volt-var response modes.
            '''

            if eut is not None:
                # Activate volt-var function with following parameters
                # SunSpec convention is to use percentages for V and Q points.
                combo_vv_vw_curve_params = {
                    'v': [(v_pairs['Vv1'] / v_nom) * 100, (v_pairs['Vv2'] / v_nom) * 100,
                          (v_pairs['Vv3'] / v_nom) * 100, (v_pairs['Vv4'] / v_nom) * 100],
                    'var': [(v_pairs['Q1'] / s_rated) * 100, (v_pairs['Q2'] / s_rated) * 100,
                            (v_pairs['Q3'] / s_rated) * 100, (v_pairs['Q4'] / s_rated) * 100],
                    'vref': round(v_nom, 2),
                    'RmpPtTms': combo_vv_vw_response_time[combo_vv_vw_curve]
                }
                ts.log_debug(f'Sending Volt-Var points: {combo_vv_vw_curve_params}')
                eut.volt_var(params={'Ena': True, 'ACTCRV': combo_vv_vw_curve, 'curve': combo_vv_vw_curve_params})
                ts.log_debug(f'Initial EUT Volt-Var settings are {eut.volt_var()}')

                # Activate volt-watt function with following parameters
                # SunSpec convention is to use percentages for V and P points.
                combo_vv_vw_curve_params = {
                    'v': [(v_pairs['VW1'] / v_nom) * 100,
                          (v_pairs['VW2'] / v_nom) * 100],
                    'w': [(v_pairs['P1'] / s_rated) * 100,
                          (v_pairs['P2'] / s_rated) * 100]
                }
                ts.log_debug(f'Sending Volt-Watt points: {combo_vv_vw_curve_params}')
                eut.volt_watt(params={'Ena': True, 'ACTCRV': combo_vv_vw_curve, 'curve': combo_vv_vw_curve_params})
                ts.log_debug(f'Initial EUT Volt-Watt settings are {eut.volt_watt()}')
            """
             (b) Set the grid source equal to the grid test voltage. Vary the energy source until the a.c. output
                of the device under test equals 100 ± 5 % of its rated active power output.
            """
            # Setting grid to vnom before test
            if grid is not None:
                grid.voltage(v_nom)
            # Setting the pvsim to the rated power of the eut
            if pv is not None:
                pv.iv_curve_config(pmp=p_rated, vmp=v_in_nom)
                pv.irradiance_set(1000.)

            """
            Going trough step C to step N
            """
            #Construct the v_steps_dict from step c to step n
            v_steps_dict = collections.OrderedDict()

            Combo_VoltVar_VoltWatt.set_step_label(starting_label='C')

            # step C
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv3']
            # step DE 1 to 5

            delta_v4_v3_step = (v_pairs['Vv4'] - v_pairs['Vv3'])/5.0
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = delta_v4_v3_step + v_pairs['Vv3']
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = 2*delta_v4_v3_step + v_pairs['Vv3']
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = 3*delta_v4_v3_step + v_pairs['Vv3']
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = 4*delta_v4_v3_step + v_pairs['Vv3']
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv4']

            # step FG 1 to 5
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv4'] - 1*delta_v4_v3_step
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv4'] - 2*delta_v4_v3_step
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv4'] - 3*delta_v4_v3_step
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv4'] - 4*delta_v4_v3_step
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv3']

            delta_v2_v1_step = (v_pairs['Vv2'] - v_pairs['Vv1'])/5.0
            # step H
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv2']
            # step IJ 1 to 5
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv2'] - 1*delta_v2_v1_step
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv2'] - 2*delta_v2_v1_step
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv2'] - 3*delta_v2_v1_step
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv2'] - 4*delta_v2_v1_step
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv1']
            # step KL 1 to 5
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = 1*delta_v2_v1_step + v_pairs['Vv1']
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = 2*delta_v2_v1_step + v_pairs['Vv1']
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = 3*delta_v2_v1_step + v_pairs['Vv1']
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = 4*delta_v2_v1_step + v_pairs['Vv1']
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vv2']
            # step MN
            v_steps_dict[Combo_VoltVar_VoltWatt.get_step_label()] = v_pairs['Vw2'] - 1

            ts.log_debug(v_steps_dict)

            dataset_filename = f'combo_vv_vw_{combo_vv_vw_curve}'
            Combo_VoltVar_VoltWatt.reset_filename(filename=dataset_filename)
            # Start the data acquisition systems
            daq.data_capture(True)

            for step_label, v_step in v_steps_dict.items():
                ts.log(f'Voltage step: setting Grid simulator voltage to {v_step} ({step_label})')
                if 'C' in step_label or 'H' in step_label:
                    if grid is not None:
                        grid.voltage(v_step)
                else:

                    Combo_VoltVar_VoltWatt.start(daq=daq, step_label=step_label)

                    if grid is not None:
                        grid.voltage(v_step)

                    Combo_VoltVar_VoltWatt.record_timeresponse(daq=daq, step_value=v_step)
                    Combo_VoltVar_VoltWatt.evaluate_criterias()
                    result_summary.write(Combo_VoltVar_VoltWatt.write_rslt_sum())

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
        """
        Configuration
        """

        mode = ts.param_value('combo_vv_vw.mode')

        """
        Test Configuration
        """
        # list of active tests
        combo_vv_vw_curves = []
        combo_vv_vw_response_time = [1, 1, 1, 1]

        # Normal combined volt-var volt-watt test (Section 5.14.4)

        v_nom = ts.param_value('eut.v_nom')
        if ts.param_value('combo_vv_vw.test_AA') == 'Enabled':
            combo_vv_vw_curves.append(1)
        if ts.param_value('combo_vv_vw.test_AB') == 'Enabled':
            combo_vv_vw_curves.append(2)
        if ts.param_value('combo_vv_vw.test_AC') == 'Enabled':
            combo_vv_vw_curves.append(3)
        if ts.param_value('combo_vv_vw.test_NZ') == 'Enabled':
            combo_vv_vw_curves.append(4)
        if ts.param_value('combo_vv_vw.test_AR') == 'Enabled':
            combo_vv_vw_curves.append(5)

        result = Combo_vv_vw_mode(combo_vv_vw_curves=combo_vv_vw_curves,
                                  combo_vv_vw_response_time=combo_vv_vw_response_time)

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


info = script.ScriptInfo(name=os.path.basename(__file__), run=run, version='1.0.0')

# combo_vv_vw test parameters
info.param_group('combo_vv_vw', label='Test Parameters')
info.param('combo_vv_vw.mode', label='combined Volt-Var and Volt-Watt mode', default='Normal', values=['Normal'])
info.param('combo_vv_vw.test_AA', label='Australia A curve', default='Enabled', values=['Disabled', 'Enabled'],
           active='combo_vv_vw.mode', active_value=['Normal'])
info.param('combo_vv_vw.test_AB', label='Australia B curve', default='Disabled', values=['Disabled', 'Enabled'],
           active='combo_vv_vw.mode', active_value=['Normal'])
info.param('combo_vv_vw.test_AC', label='Australia C curve', default='Disabled', values=['Disabled', 'Enabled'],
           active='combo_vv_vw.mode', active_value=['Normal'])
info.param('combo_vv_vw.test_NZ', label='New Zealand curve', default='Disabled', values=['Disabled', 'Enabled'],
           active='combo_vv_vw.mode', active_value=['Normal'])
info.param('combo_vv_vw.test_AR', label='Allowed Range curve', default='Disabled', values=['Disabled', 'Enabled'],
           active='combo_vv_vw.mode', active_value=['Normal'])
info.param('combo_vv_vw.test_AR_Vw1', label='Setting Vw1', default=250,
           active='combo_vv_vw.test_AR', active_value=['Enabled'])
info.param('combo_vv_vw.test_AR_Vw2', label='Setting Vw2', default=260,
           active='combo_vv_vw.test_AR', active_value=['Enabled'])
info.param('combo_vv_vw.test_AR_Vv1', label='Setting Vv1', default=200,
           active='combo_vv_vw.test_AR', active_value=['Enabled'])
info.param('combo_vv_vw.test_AR_Vv2', label='Setting Vv2', default=220,
           active='combo_vv_vw.test_AR', active_value=['Enabled'])
info.param('combo_vv_vw.test_AR_Vv3', label='Setting Vv3', default=240,
           active='combo_vv_vw.test_AR', active_value=['Enabled'])
info.param('combo_vv_vw.test_AR_Vv4', label='Setting Vv4', default=260,
           active='combo_vv_vw.test_AR', active_value=['Enabled'])

# EUT general parameters
info.param_group('eut', label='EUT Parameters', glob=True)
info.param('eut.phases', label='Phases', default='Single Phase', values=['Single phase', 'Split phase', 'Three phase'])
info.param('eut.s_rated', label='Apparent power rating (VA)', default=10000.0)
info.param('eut.p_rated', label='Output power rating (W)', default=8000.0)
info.param('eut.p_min', label='Minimum Power Rating(W)', default=1000.)
info.param('eut.var_rated', label='Output var rating (vars)', default=2000.0)
info.param('eut.v_nom', label='Nominal AC voltage (V)', default=120.0, desc='Nominal voltage for the AC simulator.')
info.param('eut.v_low', label='Minimum AC voltage (V)', default=116.0)
info.param('eut.v_high', label='Maximum AC voltage (V)', default=132.0)
info.param('eut.v_in_nom', label='V_in_nom: Nominal input voltage (Vdc)', default=400)
info.param('eut.f_nom', label='Nominal AC frequency (Hz)', default=60.0)
info.param('eut.f_max', label='Maximum frequency in the continuous operating region (Hz)', default=66.)
info.param('eut.f_min', label='Minimum frequency in the continuous operating region (Hz)', default=56.)
info.param('eut.imbalance_resp', label='EUT response to phase imbalance is calculated by:',
           default='EUT response to the average of the three-phase effective (RMS)',
           values=['EUT response to the individual phase voltages',
                   'EUT response to the average of the three-phase effective (RMS)',
                   'EUT response to the positive sequence of voltages'])



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
