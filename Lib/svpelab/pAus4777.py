"""
Copyright (c) 2018, CSIRO, SunSpec Alliance and CanmetENERGY(Natural Resources Canada)
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

Redistributions of source code must retain the above copyright notice, this
list of conditions and the following disclaimer.

Redistributions in binary form must reproduce the above copyright notice, this
list of conditions and the following disclaimer in the documentation and/or
other materials provided with the distribution.

Neither the names of CSIRO and CanmetENERGY(Natural Resources Canada)
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

"""

import os
import xml.etree.ElementTree as ET
import csv
import math
import xlsxwriter
import traceback
from datetime import datetime, timedelta
from collections import OrderedDict
import time
import collections
import numpy as np
import pandas as pd
import random
# import sys
# import os
# import glob
# import importlib

VERSION = '1.0.1'
LATEST_MODIFICATION = '4th August 2020'

FW = 'FW'  # Frequency-Watt
CPF = 'CPF'  # Constant Power Factor
VW = 'VW'  # Volt_Watt
VV = 'VV'  # Volt-Var
WV = 'WV'  # Watt-Var
CRP = 'CRP'  # Constant Reactive Power
LAP = 'LAP'  # Limit Active Power
PRI = 'PRI'  # Priority
IOP = 'IOP'  # Interoperability Tests
LV = 'LV'
HV = 'HV'

FULL_NAME = {'V': 'Voltage',
             'P': 'Active Power',
             'Q': 'Reactive Power',
             'F': 'Frequency',
             'PF': 'Power Factor'}

def VersionValidation(script_version):
    if script_version != VERSION:
        raise pAus4777Error(f'Error in pAus4777 library version is {VERSION} while script version is {script_version}.'
                            f'Update library and script version accordingly.')
    else:
        pass

class pAus4777Error(Exception):
    pass
"""
This section is for EUT parameters needed such as V, P, Q, etc.
"""

class EutParameters(object):
    def __init__(self, ts):
        self.ts = ts
        try:
            self.v_nom = ts.param_value('eut.v_nom')
            self.s_rated = ts.param_value('eut.s_rated')

            '''
            Minimum required accuracy (MRA) (per Table 3 of IEEE Std 1547-2018)

            Table 3 - Minimum measurement and calculation accuracy requirements for manufacturers
            ______________________________________________________________________________________________
            Time frame                  Steady-state measurements      
            Parameter       Minimum measurement accuracy    Measurement window      Range
            ______________________________________________________________________________________________        
            Voltage, RMS    (+/- 1% Vnom)                   10 cycles               0.5 p.u. to 1.2 p.u.
            Frequency       10 mHz                          60 cycles               50 Hz to 66 Hz
            Active Power    (+/- 5% Srated)                 10 cycles               0.2 p.u. < P < 1.0
            Reactive Power  (+/- 5% Srated)                 10 cycles               0.2 p.u. < Q < 1.0
            Time            1% of measured duration         N/A                     5 s to 600 s 
            ______________________________________________________________________________________________
                                        Transient measurements
            Parameter       Minimum measurement accuracy    Measurement window      Range
            Voltage, RMS    (+/- 2% Vnom)                   5 cycles                0.5 p.u. to 1.2 p.u.
            Frequency       100 mHz                         5 cycles                50 Hz to 66 Hz
            Time            2 cycles                        N/A                     100 ms < 5 s
            ______________________________________________________________________________________________
            '''
            self.MRA={
                'V': 0.01*self.v_nom,
                'Q': 0.05*ts.param_value('eut.s_rated'),
                'P': 0.05*ts.param_value('eut.s_rated'),
                'F': 0.01,
                'T': 0.01
            }

            self.MRA_V_trans = 0.02 * self.v_nom
            self.MRA_F_trans = 0.1
            self.MRA_T_trans = 2. / 60.

            if ts.param_value('eut.f_nom'):
                self.f_nom = ts.param_value('eut.f_nom')
            else:
                self.f_nom = None
            if ts.param_value('eut.phases') is not None:
                self.phases = ts.param_value('eut.phases')
            else:
                self.phases = None
            if ts.param_value('eut.p_rated') is not None:
                self.p_rated = ts.param_value('eut.p_rated')
                self.p_rated_prime = ts.param_value('eut.p_rated_prime')  # absorption power
                if self.p_rated_prime is None:
                    self.p_rated_prime = -self.p_rated
                self.p_min = ts.param_value('eut.p_min')
                self.var_rated = ts.param_value('eut.var_rated')
            else:
                self.var_rated = None
            # self.imbalance_angle_fix = imbalance_angle_fix
            self.absorb = ts.param_value('eut.abs_enabled')

        except Exception as e:
            self.ts.log_error('Incorrect Parameter value : %s' % e)
            raise

"""
This section is utility function needed to run the scripts such as data acquisition.
"""

class UtilParameters:
    def __init__(self):
        self.step_label = None
        self.pwr = 1.0
        self.region = ''
        self.filename = None

    def reset_curve(self, region='AA'):
        self.region = region
        self.ts.log_debug(f'P4777 Library curve has been set {region}')

    def reset_pwr(self, pwr=1.0):
        self.pwr = pwr
        self.ts.log_debug(f'P4777 Library power level has been set {round(pwr*100)}%')

    def reset_filename(self, filename):
        self.filename = filename
        self.ts.log_debug(f'P4777 Library filename has been set to {filename}')

    def set_step_label(self, starting_label=None):
        """
        Write step labels in alphabetical order as shown in the standard
        :param starting_label:
        :return: nothing
        """
        self.double_letter_label = False

        if starting_label is None:
            starting_label = 'a'
        starting_label_value = ord(starting_label)
        self.step_label = starting_label_value

    """
    Getter functions
    """
    def get_params(self, function, region=None):

        if region == None:
            return self.param[function]
        else:
            return self.param[function][region]

    def get_step_label(self):
        """
        get the step labels and increment in alphabetical order as shown in the standard
        :param: None
        :return: nothing
        """
        if self.step_label > 90:
            self.step_label = ord('A')
            self.double_letter_label = True

        if self.double_letter_label:
            step_label = 'Step {}{}'.format(chr(self.step_label), chr(self.step_label))
        else:
            step_label = 'Step {}'.format(chr(self.step_label))

        self.step_label += 1
        return step_label

    def get_measurement_label(self, type_meas):
        """
        Returns the measurement label for a measurement type

        :param type_meas:   (str) Either V, P, PF, I, F, VA, or Q
        :return:            (list of str) List of labeled measurements, e.g., ['AC_VRMS_1', 'AC_VRMS_2', 'AC_VRMS_3']
        """

        meas_root = self.type_meas[type_meas]

        if self.phases == 'Single phase':
            meas_label = [meas_root + '_1']
        elif self.phases == 'Split phase':
            meas_label = [meas_root + '_1', meas_root + '_2']
        elif self.phases == 'Three phase':
            meas_label = [meas_root + '_1', meas_root + '_2', meas_root + '_3']

        return meas_label

    def get_measurement_total(self, data, type_meas, log=False):
        """
        Sum or average the EUT values from all phases

        :param data:        dataset from data acquisition object
        :param type_meas:   Either V,P or Q
        :param log:         Boolean variable to disable or enable logging
        :return: Any measurements from the DAQ
        """
        value = None
        nb_phases = None

        try:
            if self.phases == 'Single phase':
                value = data.get(self.get_measurement_label(type_meas)[0])
                if log:
                    self.ts.log_debug('        %s are: %s'
                                      % (self.get_measurement_label(type_meas), value))
                nb_phases = 1

            elif self.phases == 'Split phase':
                value1 = data.get(self.get_measurement_label(type_meas)[0])
                value2 = data.get(self.get_measurement_label(type_meas)[1])
                if log:
                    self.ts.log_debug('        %s are: %s, %s'
                                      % (self.get_measurement_label(type_meas), value1, value2))
                value = value1 + value2
                nb_phases = 2

            elif self.phases == 'Three phase':
                value1 = data.get(self.get_measurement_label(type_meas)[0])
                value2 = data.get(self.get_measurement_label(type_meas)[1])
                value3 = data.get(self.get_measurement_label(type_meas)[2])
                if log:
                    self.ts.log_debug('        %s are: %s, %s, %s'
                                      % (self.get_measurement_label(type_meas), value1, value2, value3))
                value = value1 + value2 + value3
                nb_phases = 3

        except Exception as e:
            self.ts.log_error('Inverter phase parameter not set correctly.')
            self.ts.log_error('phases=%s' % self.phases)
            raise pAus4777Error('Error in get_measurement_total() : %s' % (str(e)))

        # TODO : imbalance_resp should change the way you acquire the data
        if type_meas == 'V':
            # average value of V
            value = value / nb_phases
        elif type_meas == 'F':
            # No need to do data average for frequency
            value = data.get(self.get_measurement_label(type_meas)[0])

        return round(value, 3)

    def get_script_name(self):
        if self.script_complete_name is None:
            self.script_complete_name = 'Script name not initialized'
        return self.script_complete_name

class DataLogging:
    def __init__(self):
        self.type_meas = {'V': 'AC_VRMS', 'I': 'AC_IRMS', 'P': 'AC_P', 'Q': 'AC_Q', 'VA': 'AC_S',
                          'F': 'AC_FREQ', 'PF': 'AC_PF'}

        self.rslt_sum_col_name = ''
        self.sc_points = {}
        #self._config()
        self.set_sc_points()
        self.set_result_summary_name()
        self.tr = None
        self.n_tr = None
        self.initial_value = {}
        self.tr_value = collections.OrderedDict()
        self.current_step_label = None
    #def __config__(self):

    def reset_time_settings(self, tr, number_tr=2):
        self.tr = tr
        self.ts.log_debug(f'P4777 Time response has been set to {self.tr} seconds')
        self.n_tr = number_tr
        self.ts.log_debug(f'P4777 Number of Time response has been set to {self.n_tr} cycles')

    def set_sc_points(self):
        """
        Set SC points for DAS depending on which measured variables initialized and targets

        :return: None
        """
        # TODO : The target value are in percentage (0-100) and something in P.U. (0-1.0)
        #       The measure value are in absolute value

        xs = self.x_criteria
        ys = list(self.y_criteria.keys())
        row_data = []

        for meas_value in self.meas_values:
            row_data.append('%s_MEAS' % meas_value)

            if meas_value in xs:
                row_data.append('%s_TARGET' % meas_value)

            elif meas_value in ys:
                row_data.append('%s_TARGET' % meas_value)
                row_data.append('%s_TARGET_MIN' % meas_value)
                row_data.append('%s_TARGET_MAX' % meas_value)

        row_data.append('EVENT')
        self.ts.log_debug('Sc points: %s' % row_data)
        self.sc_points['sc'] = row_data

    def set_result_summary_name(self):
        """
        Write column names for results file depending on which test is being run
        :param nothing:
        :return: nothing
        """
        xs = self.x_criteria
        ys = self.y_criteria
        row_data = []


        # Time response criteria will take last placed value of Y variables
        for y in ys:
            row_data.append(f'{y}_BEFORE_RCT_1S')
            row_data.append(f'{y}_BEFORE_RCT_10s')

        for meas_value in self.meas_values:
            row_data.append('%s_MEAS' % meas_value)

            if meas_value in xs:
                row_data.append('%s_TARGET' % meas_value)

            elif meas_value in ys:
                row_data.append('%s_TARGET' % meas_value)
                row_data.append('%s_TARGET_MIN' % meas_value)
                row_data.append('%s_TARGET_MAX' % meas_value)

        row_data.append('STEP')
        row_data.append('FILENAME')

        self.rslt_sum_col_name = ','.join(row_data) + '\n'

    def get_rslt_param_plot(self, x_axis_specs=None):
        """
        This getters function creates and returns all the predefined columns for the plotting process
        :return: result_params
        """
        if x_axis_specs is None:
            x_axis_specs = {'min': 'Not congigured'}

        y_variables = self.y_criteria
        x_variables = self.x_criteria

        # For VV, VW and FW
        y_points = []
        x_points = []
        y_title = []
        x_title = []

        # y_points = '%s_TARGET,%s_MEAS' % (y, y)
        # y2_points = '%s_TARGET,%s_MEAS' % (y2, y2)

        for y in y_variables:
            self.ts.log_debug('y_temp: %s' % y)
            # y_temp = self.get_measurement_label('%s' % y)
            y_temp = '{}'.format(','.join(str(x) for x in self.get_measurement_label('%s' % y)))
            y_title.append(FULL_NAME[y])
            y_points.append(y_temp)
        self.ts.log_debug('y_points: %s' % y_points)
        y_points = ','.join(y_points)
        y_title = ','.join(y_title)

        for x in x_variables:
            self.ts.log_debug('x_variable for result: %s' % x)
            x_temp = '{}'.format(','.join(str(x) for x in self.get_measurement_label('%s' % x)))
            x_title.append(FULL_NAME[x])
            x_points.append(x_temp)
        x_points = ','.join(x_points)
        x_title = ','.join(x_title)

        result_params = {
            'plot.title': 'title_name',
            'plot.x.title': x_title,
            'plot.x.points': x_points,
            'plot.x.axis.min': x_axis_specs['min'],
            'plot.y.points': y_points,
            'plot.y.title': y_title,
            'plot.%s_TARGET.min_error' % y: '%s_TARGET_MIN' % y,
            'plot.%s_TARGET.max_error' % y: '%s_TARGET_MAX' % y,
        }

        return result_params

    def get_sc_points(self):
        """
        This getters function returns the sc points for DAS
        :return:            self.sc_points
        """
        return self.sc_points

    def get_rslt_sum_col_name(self):
        """
        This getters function returns the column name for result_summary.csv
        :return:            self.rslt_sum_col_name
        """
        return self.rslt_sum_col_name

    def write_rslt_sum(self):
        """
        Combines the analysis results, the step label and the filenamoe to return
        a row that will go in result_summary.csv
        :param analysis: Dictionary with all the information for result summary

        :param step:   test procedure step letter or number (e.g "Step G")
        :param filename: the dataset filename use for analysis

        :return: row_data a string with all the information for result_summary.csv
        """

        xs = self.x_criteria
        ys = list(self.y_criteria.keys())
        last_iter = 2
        row_data = []

        # Time response criteria will take last placed value of Y variables
        for y in ys:
            row_data.append(str(self.tr_value[f'{y}_T_COM_{1}_PF']))
            row_data.append(str(self.tr_value[f'{y}_T_COM_{2}_PF']))


        # Default measured values are V, P and Q (F can be added) refer to set_meas_variable function
        for meas_value in self.meas_values:
            row_data.append(str(self.tr_value['%s_T_COM_%d' % (meas_value, last_iter)]))
            # Variables needed for variations
            if meas_value in xs:
                row_data.append(str(self.tr_value['%s_T_COM_TARG_%d' % (meas_value, last_iter)]))
            # Variables needed for criteria verifications with min max passfail
            if meas_value in ys:
                #self.ts.log_debug(f'{}')
                row_data.append(str(self.tr_value['%s_T_COM_TARG_%s' % (meas_value, last_iter)]))
                row_data.append(str(self.tr_value['%s_T_COM_%s_MIN' % (meas_value, last_iter)]))
                row_data.append(str(self.tr_value['%s_T_COM_%s_MAX' % (meas_value, last_iter)]))

        row_data.append(self.current_step_label)
        row_data.append(str(self.filename))
        row_data_str = ','.join(row_data) + '\n'

        return row_data_str

        # except Exception as e:
        #     raise p1547Error('Error in write_rslt_sum() : %s' % (str(e)))

    def start(self, daq, step_label):
        """
        Sum the EUT reactive power from all phases
        :param daq:         data acquisition object from svpelab library
        :param step:        test procedure step letter or number (e.g "Step G")
        :return: returns a dictionary with the timestamp, event and total EUT reactive power
        """
        # TODO : In a more sophisticated approach, get_initial['timestamp'] will come from a
        #  reliable secure thread or data acquisition timestamp

        self.initial_value['timestamp'] = datetime.now()
        self.current_step_label = step_label
        daq.sc['EVENT'] = self.current_step_label + '_INIT'
        daq.data_sample()
        data = daq.data_capture_read()
        daq.sc['EVENT'] = self.current_step_label
        if isinstance(self.x_criteria, list):
            for xs in self.x_criteria:
                self.initial_value[xs] = {'x_value': self.get_measurement_total(data=data, type_meas=xs, log=False)}
                daq.sc['%s_MEAS' % xs] = self.initial_value[xs]['x_value']
        else:
            self.initial_value[self.x_criteria] = {'x_value': self.get_measurement_total(data=data, type_meas=self.x_criteria, log=False)}
            daq.sc['%s_MEAS' % self.x_criteria] = self.initial_value[self.x_criteria]['x_value']

        if isinstance(self.y_criteria, list):
            for ys in self.y_criteria:
                self.initial_value[ys] = {'y_value': self.get_measurement_total(data=data, type_meas=ys, log=False)}
                daq.sc['%s_MEAS' % ys] = self.initial_value[ys]["y_value"]
        elif isinstance(self.y_criteria, dict):
            for ys in list(self.y_criteria.keys()):
                self.initial_value[ys] = {'y_value': self.get_measurement_total(data=data, type_meas=ys, log=False)}
                daq.sc['%s_MEAS' % ys] = self.initial_value[ys]["y_value"]
        else:
            self.initial_value[self.y_criteria] = {'y_value': self.get_measurement_total(data=data, type_meas=self.y_criteria, log=False)}
            daq.sc['%s_MEAS' % self.y_criteria] = self.initial_value[self.y_criteria]['y_value']
        daq.data_sample()

        #return self.initial_value

    def record_timeresponse(self, daq, step_value, pwr_lvl=1.0, curve=1, x_target=None, y_target=None):
        """
        Get the data from a specific time response (tr) corresponding to x and y values returns a dictionary
        but also writes in the soft channels of the DAQ system
        :param daq:             data acquisition object from svpelab library
        :param initial_value:   the dictionary with the initial values (X, Y and timestamp)
        :param pwr_lvl:         The input power level in p.u.
        :param curve:           The characteristic curve number
        :param x_target:        The target value of X value (e.g. FW -> f_step)
        :param y_target:        The target value of Y value (e.g. LAP -> act_pwrs_limits)
        :param n_tr:            The number of time responses used to validate the response and steady state values

        :return: returns a dictionary with the timestamp, event and total EUT reactive power
        """

        x = self.x_criteria
        y = list(self.y_criteria.keys())
        T_Com_names = {1: '1S', 2: '10S', 3: '20S'}
        tr_list = []

        for i in range(self.n_tr):
            tr_list.append(self.initial_value['timestamp'] + timedelta(seconds=self.tr[i]))
            for meas_value in self.meas_values:
                self.tr_value['%s_T_COM_%s' % (meas_value, i)] = None
                if meas_value in x:
                    self.tr_value['%s_T_COM_TARG_%s' % (meas_value, i)] = None
                elif meas_value in y:
                    self.tr_value['%s_T_COM_TARG_%s' % (meas_value, i)] = None
                    self.tr_value['%s_T_COM_%s_MIN' % (meas_value, i)] = None
                    self.tr_value['%s_T_COM_%s_MAX' % (meas_value, i)] = None
        tr_iter = 1

        for tr_ in tr_list:
            now = datetime.now()
            if now <= tr_:
                time_to_sleep = tr_ - datetime.now()
                self.ts.log('Waiting %s seconds to get the next Tr data for analysis...' %
                            time_to_sleep.total_seconds())
                self.ts.sleep(time_to_sleep.total_seconds())
            daq.sc['EVENT'] = "{0}_T_COM_{1}".format(self.current_step_label, T_Com_names[tr_iter])
            daq.data_sample()  # sample new data
            data = daq.data_capture_read()  # Return dataset created from last data capture

            # update the meas values in the dataset
            self.update_measure_value(data, daq)

            daq.sc['EVENT'] = "{0}_T_COM".format(self.current_step_label)
            # update daq.sc values for Y_TARGET, Y_TARGET_MIN, and Y_TARGET_MAX

            # store the daq.sc['Y_TARGET'], daq.sc['Y_TARGET_MIN'], and daq.sc['Y_TARGET_MAX'] in tr_value

            for meas_value in self.meas_values:
                try:
                    self.tr_value['%s_T_COM_%s' % (meas_value, tr_iter)] = daq.sc['%s_MEAS' % meas_value]

                    self.ts.log('Value %s: %s' % (meas_value, daq.sc['%s_MEAS' % meas_value]))
                    if meas_value in x:
                        daq.sc['%s_TARGET' % meas_value] = step_value
                        self.tr_value['%s_T_COM_TARG_%s' % (meas_value, tr_iter)] = step_value
                        self.ts.log('X Value (%s) = %s' % (meas_value, daq.sc['%s_MEAS' % meas_value]))
                    elif meas_value in y:
                        self.ts.log_debug(f'{meas_value} and {y}')
                        daq.sc['%s_TARGET' % meas_value] = self.update_target_value(value=step_value,
                                                                                    function=self.y_criteria[meas_value])
                        daq.sc['%s_TARGET_MIN' % meas_value], daq.sc['%s_TARGET_MAX' % meas_value] =\
                            self.calculate_min_max_values(data=data, function=self.y_criteria[meas_value])

                        self.tr_value[f'{meas_value}_T_COM_TARG_{tr_iter}'] = daq.sc['%s_TARGET' % meas_value]
                        self.tr_value[f'{meas_value}_T_COM_{tr_iter}_MIN'] = daq.sc['%s_TARGET_MIN' % meas_value]
                        self.tr_value[f'{meas_value}_T_COM_{tr_iter}_MAX'] = daq.sc['%s_TARGET_MAX' % meas_value]
                        self.ts.log('Y Value (%s) = %s. Pass/fail bounds = [%s, %s]' %
                                     (meas_value, daq.sc['%s_MEAS' % meas_value],
                                      daq.sc['%s_TARGET_MIN' % meas_value], daq.sc['%s_TARGET_MAX' % meas_value]))
                except Exception as e:
                    self.ts.log_debug('Measured value (%s) not recorded: %s' % (meas_value, e))
                    raise
            #self.tr_value[tr_iter]["timestamp"] = tr_
            self.tr_value[f'timestamp_{tr_iter}'] = tr_
            tr_iter = tr_iter + 1


        return self.tr_value

        # except Exception as e:
        #    raise p1547Error('Error in get_tr_data(): %s' % (str(e)))

    def update_target_value(self, value, function):

        if function == VV:
            vv_pairs=self.get_params(function=VV, region=self.region)
            x = [vv_pairs['Vv1'], vv_pairs['Vv2'],
                 vv_pairs['Vv3'], vv_pairs['Vv4']]
            y = [vv_pairs['Q1'], vv_pairs['Q2'],
                 vv_pairs['Q3'], vv_pairs['Q4']]
            q_value = float(np.interp(value, x, y))
            q_value *= self.pwr
            return round(q_value, 1)

        if function == VW:
            vw_pairs = self.get_params(function=VW, region=self.region)
            x = [vw_pairs['Vw1'], vw_pairs['Vw2']]
            y = [vw_pairs['P1'], vw_pairs['P2']]
            p_value = float(np.interp(value, x, y))
            p_value *= self.pwr
            return round(p_value, 1)

    def calculate_min_max_values(self, data, function):
        if function == VV:

            v_meas = self.get_measurement_total(data=data, type_meas='V', log=False)
            target_min = self.update_target_value(v_meas + self.MRA['V'] * 1.5, function=VV) - (self.MRA['Q'] * 1.5)
            target_max = self.update_target_value(v_meas - self.MRA['V'] * 1.5, function=VV) + (self.MRA['Q'] * 1.5)

            return target_min, target_max

        elif function == VW:

            v_meas = self.get_measurement_total(data=data, type_meas='V', log=False)
            target_min = self.update_target_value(v_meas + self.MRA['V'] * 1.5, function=VW) - (self.MRA['P'] * 1.5)
            target_max = self.update_target_value(v_meas - self.MRA['V'] * 1.5, function=VW) + (self.MRA['P'] * 1.5)

            return target_min, target_max

class CriteriaValidation:
    def __init__(self):
        pass

    def evaluate_criterias(self):
        self.response_time_criterias()

    def response_time_criterias(self):
        """
            Response time criterias : The Eut needs to begin his response to a voltage regulation demand before the
            response commencement time. Then, it needs to have responded before the response completion time.


            Y_final. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .-------|
            Y_Tcompletion_10s. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . ./
                                                                                                    -    .
                                                                                               /         .
                                                                                           -             .
                                                                                      |                  .
                                                                                     |                   .
                                                                                    |                    .
                                                                                  -                      .
                                                                                /                        .
                                                                            -                            .
            Y_Tcompletion_1s. . . . . . . . . . . . . . . . . . . . . . . . ./                                  .
                                                               -      .                                  .
                                                        /             .                                  .
            Y_initial. .|----------------------------                 .                                  .
                         |                                            |                                  |
                    t_initial                                       Tcom_1s                           Tcom_10s



                (DR AS/NZS 4777.2-2020) Where a power quality response mode is enabled the inverter shall commence
                and complete the required response according to the defined characteristics of Clause 3.3.2 within
                the relevant times specified in Table 3.5. Response times faster than the maximum times in Table 3.5
                are permitted, and commencement and completion of the inverter response should not be unnecessarily
                delayed or slowed.
                            Table 3.5 — Power quality response modes — Maximum response times
            +------------------------------------------------------------+----------------------------------------+
            |      Region      |       Response Commencement Time        |        Response Completion Time        |
            +------------------------------------------------------------+----------------------------------------+
            |       All        |                   1s                    |                  10s                   |
            +------------------------------------------------------------+----------------------------------------+

            Pass/Fail Criterias:
                1) |Y_Tcompletion_1s - Y_initial| > 2*Y_tol (Y_tol = 4%*S_Rated)
                2) |Y_final - Y_Tcom_10s| < 2*Y_tol

        """
        #self.ts.log_debug("Writing parameters:")
        #for key in self.__dict__.keys():
        #    self.ts.log_debug(key)
        #self.ts.log_debug("Parameters written.")

        #self.ts.log_debug(self.tr_value)
        #for odict in self.tr_value:
        #    self.ts.log_debug(f'Key =  {odict}')
        s_rated = self.s_rated
        #self.ts.log_debug(f's_rated = {s_rated}')
        q_current = self.tr_value['Q_T_COM_TARG_2'];
        #self.ts.log_debug(f'q_current = {q_current}')
        p_limit = math.sqrt(s_rated*s_rated - q_current*q_current)
        #self.ts.log_debug(f'p_limit = {p_limit}')

        for y in list(self.y_criteria.keys()):
            y_tol = self.s_rated * 0.04
            y_initial = self.initial_value[y]["y_value"]
            y_final = self.tr_value[f'{y}_T_COM_TARG_{2}']
            y_Tcompletion_1s = self.tr_value[f'{y}_T_COM_{1}']
            y_Tcompletion_10s = self.tr_value[f'{y}_T_COM_{2}']

            y_final_eval = abs(y_final - y_Tcompletion_10s)
            y_final_eval_str = f'|{y_final:.2f} - {y_Tcompletion_10s:.2f}| <='  # TODO CHANGED FROM y_Tcompletion_1s
            if y == 'P':
                self.ts.log_debug('P registered')
                y_final_eval = y_Tcompletion_10s - y_final
                y_final_eval_str = f'{y_Tcompletion_10s:.2f} - {y_final:.2f} <='  # TODO CHANGED FROM y_Tcompletion_1s
            else:
                self.ts.log_debug('Q registered')
            y_tol = self.s_rated * 0.04


            # pass/fail assessment for the response commencement time
            if abs(y_Tcompletion_1s - y_initial) >= 2*y_tol:
                self.tr_value[f'{y}_T_COM_{1}_PF'] = 'Pass'
            else:
                self.tr_value[f'{y}_T_COM_{1}_PF'] = 'Fail'

            self.ts.log_debug(f' Response commencement time 1.2s for {y}, evaluation : '
                              f'|{y_Tcompletion_1s:.2f} - {y_initial:.2f}| >='
                              f' {2*y_tol:.2f}' + '[%s]' % (self.tr_value[f"{y}_T_COM_{1}_PF"]))

            # pass/fail assessment for the response completion time
            if y_final_eval <= 2*y_tol:
                self.tr_value[f'{y}_T_COM_{2}_PF'] = 'Pass'
            else:
                self.tr_value[f'{y}_T_COM_{2}_PF'] = 'Fail'

            #self.ts.log_debug(f' Response completion time 10.2s for {y}, evaluation : '
            #                  f'|{y_final:.2f} - {y_Tcompletion_1s:.2f}| <='
            #                  f' {2 * y_tol:.2f}' + '[%s]' % (self.tr_value[f"{y}_T_COM_{2}_PF"]))

            self.ts.log_debug(f' Response completion time 10.2s for {y}, evaluation : {y_final_eval_str}'
                              f' {2 * y_tol:.2f}' + '[%s]' % (self.tr_value[f"{y}_T_COM_{2}_PF"]))

class ImbalanceComponent:
    pass

"""
Section reserved for HIL model object
"""

class HilModel(object):
    def __init__(self, ts, support_interfaces):
        self.params = {}
        self.parameters_dic = {}
        self.mode = []
        self.ts = ts
        self.start_time = None
        self.stop_time = None
        if support_interfaces.get('hil') is not None:
            self.hil = support_interfaces.get('hil')
        else:
            self.hil = None

    def set_model_on(self):
        """
        Set the HIL model on
        """
        model_name = self.params["model_name"]
        self.hil.set_params(model_name + "/SM_Source/SVP Commands/mode/Value", 3)

    """
    Getter functions
    """

    def get_model_parameters(self, current_mode):
        self.ts.log(f'Getting HIL parameters for {current_mode}')
        return self.parameters_dic[current_mode], self.start_time, self.stop_time

    def get_waveform_config(self, current_mode, offset):
        params = {}
        params["start_time_value"] = float(self.start_time - offset)
        params["end_time_value"] = float(self.stop_time + offset)
        params["start_time_variable"] = "Tstart"
        params["end_time_variable"] = "Tend"
        return params

"""
This section is for Voltage stabilization function such as VV, VW, CPF and CRP
"""

#class VoltVar(EutParameters, UtilParameters, DataLogging, CriteriaValidation):
class VoltVar(EutParameters):

    meas_values = ['V', 'Q', 'P']
    x_criteria = ['V']
    y_criteria = {'Q': VV}
    script_complete_name = 'Volt-Var'

    def __init__(self, ts):
        VoltVar.set_params(self)
        # Create the pairs need

    def set_params(self):
        self.param[VV] = {}
        self.param[VV]['AA'] = {
            'Vv1': round((207./230.) * self.v_nom, 2),
            'Vv2': round((220./230.) * self.v_nom, 2),
            'Vv3': round((240./230.) * self.v_nom, 2),
            'Vv4': round((258./230.) * self.v_nom, 2),
            'Q1': round(self.s_rated * 0.44, 2),
            'Q2': round(self.s_rated * 0.0, 2),
            'Q3': round(self.s_rated * 0.0, 2),
            'Q4': round(self.s_rated * -0.60, 2)
        }

        self.param[VV]['AB'] = {
            'Vv1': round((205./230.) * self.v_nom, 2),
            'Vv2': round((220./230.) * self.v_nom, 2),
            'Vv3': round((235./230.) * self.v_nom, 2),
            'Vv4': round((255./230.) * self.v_nom, 2),
            'Q1': round(self.s_rated * 0.3, 2),
            'Q2': round(self.s_rated * 0, 2),
            'Q3': round(self.s_rated * 0, 2),
            'Q4': round(self.s_rated * -0.4, 2)
        }

        self.param[VV]['AC'] = {
            'Vv1': round((215./230.) * self.v_nom, 2),
            'Vv2': round((230./230.) * self.v_nom, 2),
            'Vv3': round((240./230.) * self.v_nom, 2),
            'Vv4': round((255./230.) * self.v_nom, 2),
            'Q1': round(self.s_rated * 0.44, 2),
            'Q2': round(self.s_rated * 0, 2),
            'Q3': round(self.s_rated * 0, 2),
            'Q4': round(self.s_rated * -0.6, 2)
        }

        self.param[VV]['NZ'] = {
            'Vv1': round((207./230.) * self.v_nom, 2),
            'Vv2': round((220./230.) * self.v_nom, 2),
            'Vv3': round((235./230.) * self.v_nom, 2),
            'Vv4': round((244./230.) * self.v_nom, 2),
            'Q1': round(self.s_rated * 0.60, 2),
            'Q2': round(self.s_rated * 0, 2),
            'Q3': round(self.s_rated * 0, 2),
            'Q4': round(self.s_rated * -0.6, 2)
        }
        self.ts.log_debug(f'{self.param[VV]}')


    def create_vv_dict_steps(self, mode=None, secondary_pairs=None):
        pass

    def update_target_value(self, value):

        x = [self.param[self.region]['Vv1'], self.param[self.region]['Vv2'],
             self.param[self.region]['Vv3'], self.param[self.region]['Vv4']]
        y = [self.param[self.region]['Q1'], self.param[self.region]['Q2'],
             self.param[self.region]['Q3'], self.param[self.region]['Q4']]
        q_value = float(np.interp(value, x, y))
        q_value *= self.pwr
        return round(q_value, 1)

    def update_measure_value(self, data, daq):

        daq.sc['V_MEAS'] = self.get_measurement_total(data=data, type_meas='V', log=False)
        daq.sc['P_MEAS'] = self.get_measurement_total(data=data, type_meas='P', log=False)
        daq.sc['Q_MEAS'] = self.get_measurement_total(data=data, type_meas='Q', log=False)

    def calculate_min_max_values(self, daq, data):
        v_meas = self.get_measurement_total(data=data, type_meas='V', log=False)
        target_min = self.update_target_value(v_meas) - 0.04*self.s_rated
        target_max = self.update_target_value(v_meas) + 0.04*self.s_rated


class VoltWatt():

    """
    param curve: choose curve characterization [1-3] 1 is default
    """
    meas_values = ['V', 'Q', 'P']
    x_criteria = ['V']
    y_criteria = {'P': VW}
    script_complete_name = 'Volt-Watt'

    def __init__(self, ts):
        VoltWatt.set_params(self)

    def set_params(self, region='AA'):
        """
        Function to create dictionnary with all characteristics curves/regions available
        :return: Nothing
        """
        self.param[VW] = {}
        self.param[VW]['AA'] = {
            'Vw1': round((253./230.) * self.v_nom, 2),
            'Vw2': round((260./230.) * self.v_nom, 2),
            'P1': round(1.0*self.p_rated, 2),
            'P2': round(0.2*self.p_rated, 2)
        }
        self.param[VW]['AB'] = {
            'Vw1': round((250./230.) * self.v_nom, 2),
            'Vw2': round((260./230.) * self.v_nom, 2),
            'P1': round(1.0*self.p_rated, 2),
            'P2': round(0.2*self.p_rated, 2)
        }
        self.param[VW]['AC'] = {
            'Vw1': round((253./230.) * self.v_nom, 2),
            'Vw2': round((260./230.) * self.v_nom, 2),
            'P1': round(1.0*self.p_rated, 2),
            'P2': round(0.2*self.p_rated, 2)
        }
        self.param[VW]['NZ'] = {
            'Vw1': round((242./230.) * self.v_nom, 2),
            'Vw2': round((250./230.)* self.v_nom, 2),
            'P1': round(1.0*self.p_rated, 2),
            'P2': round(0.2*self.p_rated, 2)
        }
        #TODO incorporate Allowed Range
        """
        self.param['Allowed range'] = {
            'V1': round(1.09 * self.v_nom, 2),
            'V2': round(1.10 * self.v_nom, 2),
            'P1': round(self.p_rated, 2)
        }
        """
        self.ts.log(f'param={self.param[VW]}')
        #return self.param[region]

    def create_vw_dict_steps(self, mode=None, secondary_pairs=None):
        """
        Function to create dictionnary depending on which mode volt-watt is running
        :param mode: string [None, Volt-Var, etc]
        :param secondary_pairs: if mode is not none, secondary_pairs might be required to give curve points of
        the secondary function
        :return: Voltage step dictionnary
        """

        # Construct the v_steps_dict from step c to step n
        v_steps_dict = collections.OrderedDict()

        vw_pairs = self.get_params(function=VW, region=self.region)

        if mode == 'Volt-Var':
            vv_pairs = secondary_pairs

            delta_vv4_vv3_step = (vv_pairs['Vv4'] - vv_pairs['Vv3']) / 5.0
            delta_vv2_vv1_step = (vv_pairs['Vv2'] - vv_pairs['Vv1']) / 5.0

            # step CDE 1 to 5
            voltage = vv_pairs['Vv3']
            v_steps_dict['Step_C'] = voltage
            for i in range(1, 6):
                voltage += delta_vv4_vv3_step
                v_steps_dict[f'Step_D_{i}'] = round(voltage, 2)

            # step FG 1 to 5
            for i in range(1, 6):
                voltage -= delta_vv4_vv3_step
                v_steps_dict[f'Step_F_{i}'] = round(voltage, 2)

            voltage = vv_pairs['Vv2']
            v_steps_dict['Step_H'] = voltage
            # step H
            for i in range(1, 6):
                # step IJ 1 to 5
                voltage -= delta_vv2_vv1_step
                v_steps_dict[f'Step_I_{i}'] = round(voltage, 2)
            for i in range(1, 6):
                # step KL 1 to 5
                voltage += delta_vv2_vv1_step
                v_steps_dict[f'Step_K_{i}'] = round(voltage, 2)
            v_steps_dict['Step_M'] = round(vw_pairs['Vw2'] - 1.)

        else:
            delta_vw2_vw1_step = ((vw_pairs['Vw2']-1.0) - vw_pairs['Vw1']) / 5.0
            voltage = vw_pairs['Vw1']
            v_steps_dict['Step_C'] = voltage
            for i in range(1, 6):
                voltage += delta_vw2_vw1_step
                v_steps_dict[f'Step_D_{i}'] = round(voltage, 2)
            for i in range(1, 6):
                voltage -= delta_vw2_vw1_step
                v_steps_dict[f'Step_F_{i}'] = round(voltage, 2)
            v_steps_dict[f'Step_H'] = vw_pairs['Vw2']-1.0

            self.ts.log(f'v_step_dict={v_steps_dict}')

        return v_steps_dict
      
    def update_target_value(self, value):

        x = [self.param[self.region]['Vw1'], self.param[self.region]['Vw2']]
        y = [self.param[self.region]['P1'], self.param[self.region]['P2']]
        q_value = float(np.interp(value, x, y))
        q_value *= self.pwr
        return round(q_value, 1)

    def update_measure_value(self, data, daq):

        daq.sc['V_MEAS'] = self.get_measurement_total(data=data, type_meas='V', log=False)
        daq.sc['P_MEAS'] = self.get_measurement_total(data=data, type_meas='P', log=False)
        daq.sc['Q_MEAS'] = self.get_measurement_total(data=data, type_meas='Q', log=False)

    def calculate_min_max_values(self, daq, data):
        v_meas = self.get_measurement_total(data=data, type_meas='V', log=False)
        target_min = self.update_target_value(v_meas) - 0.04 * self.s_rated
        target_max = self.update_target_value(v_meas) + 0.04 * self.s_rated

class ActiveFunction(EutParameters, DataLogging, UtilParameters, CriteriaValidation, VoltWatt):
    """
    This class acts as the main function
    As multiple functions might be needed for a compliance script, this function will inherit
    of all functions if needed.
    """
    def __init__(self, ts, functions):
        # Values defined as target/step values which will be controlled as step
        x_criterias = []
        # Values defined as values which will be controlled as step
        y_criterias = []
        self.param = {}
        EutParameters.__init__(self, ts)
        UtilParameters.__init__(self)
        self.ts.log(f'Functions to be activated in this test script = {functions}')
        self.y_criteria={}

        if VW in functions:
            VoltWatt.__init__(self, ts)
            x_criterias += VoltWatt.x_criteria
            self.y_criteria.update(VoltWatt.y_criteria)
        if VV in functions:
            VoltVar.__init__(self, ts)
            x_criterias += VoltVar.x_criteria
            self.y_criteria.update(VoltVar.y_criteria)

        #Remove duplicates
        self.x_criteria = list(OrderedDict.fromkeys(x_criterias))
        #self.y_criteria=list(OrderedDict.fromkeys(y_criterias))
        self.meas_values = list(OrderedDict.fromkeys(x_criterias+list(self.y_criteria.keys())))

        DataLogging.__init__(self)
        CriteriaValidation.__init__(self)

if __name__ == "__main__":
    pass

