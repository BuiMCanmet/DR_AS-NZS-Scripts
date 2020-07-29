"""
Copyright (c) 2018, CSIRO and CanmetENERGY(Natural Resources Canada)
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

VERSION = '1.0.0'
LATEST_MODIFICATION = '22nd July 2020'

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
CAT_2 = 'CAT_2'
CAT_3 = 'CAT_3'
VOLTAGE = 'V'
FREQUENCY = 'F'
FULL_NAME = {'V': 'Voltage',
             'P': 'Active Power',
             'Q': 'Reactive Power',
             'F': 'Frequency',
             'PF': 'Power Factor'}


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
    #Default region set to B
    def __init__(self):
        self.step_label = None
        self.pwr = 1.0
        self.region = ''
        self.filename = None

    def reset_curve(self, region='Australia A'):
        self.region = region
        self.ts.log_debug(f'P1547 Librairy curve has been set {region}')

    def reset_pwr(self, pwr=1.0):
        self.pwr = pwr
        self.ts.log_debug(f'P1547 Librairy power level has been set {round(pwr*100)}%')

    def reset_filename(self, filename):
        self.filename = filename

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
    def get_params(self, region=None):

        if region == None:
            return self.param
        else:
            return self.param[region]

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
    def __init__(self, meas_values, x_criteria, y_criteria):
        self.type_meas = {'V': 'AC_VRMS', 'I': 'AC_IRMS', 'P': 'AC_P', 'Q': 'AC_Q', 'VA': 'AC_S',
                          'F': 'AC_FREQ', 'PF': 'AC_PF'}
        # Values to be recorded
        self.meas_values = meas_values
        # Values defined as target/step values which will be controlled as step
        self.x_criteria = x_criteria
        # Values defined as values which will be controlled as step
        self.y_criteria = y_criteria
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
        self.ts.log_debug(f'P1547 Time response has been set to {self.tr} seconds')
        self.n_tr = number_tr
        self.ts.log_debug(f'P1547 Number of Time response has been set to {self.n_tr} cycles')

    def set_sc_points(self):
        """
        Set SC points for DAS depending on which measured variables initialized and targets

        :return: None
        """
        # TODO : The target value are in percentage (0-100) and something in P.U. (0-1.0)
        #       The measure value are in absolute value

        xs = self.x_criteria
        ys = self.y_criteria
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
        """
        if self.criteria_mode[0]:  # transient response pass/fail
            row_data.append('90%_BY_TR=1')
        if self.criteria_mode[1]:
            row_data.append('WITHIN_BOUNDS_BY_TR=1')
        if self.criteria_mode[2]:  # steady-state accuracy
            row_data.append('WITHIN_BOUNDS_BY_LAST_TR')
        """

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

    def get_rslt_param_plot(self):
        """
        This getters function creates and returns all the predefined columns for the plotting process
        :return: result_params
        """
        y_variables = self.y_criteria
        y2_variables = self.x_criteria

        # For VV, VW and FW
        y_points = []
        y2_points = []
        y_title = []
        y2_title = []

        #y_points = '%s_TARGET,%s_MEAS' % (y, y)
        #y2_points = '%s_TARGET,%s_MEAS' % (y2, y2)

        for y in y_variables:
            self.ts.log_debug('y_temp: %s' % y)
            #y_temp = self.get_measurement_label('%s' % y)
            y_temp = '{}'.format(','.join(str(x) for x in self.get_measurement_label('%s' % y)))
            y_title.append(FULL_NAME[y])
            y_points.append(y_temp)
        self.ts.log_debug('y_points: %s' % y_points)
        y_points = ','.join(y_points)
        y_title = ','.join(y_title)

        for y2 in y2_variables:
            self.ts.log_debug('y2_variable for result: %s' % y2)
            y2_temp = '{}'.format(','.join(str(x) for x in self.get_measurement_label('%s' % y2)))
            y2_title.append(FULL_NAME[y2])
            y2_points.append(y2_temp)
        y2_points = ','.join(y2_points)
        y2_title = ','.join(y2_title)

        result_params = {
            'plot.title': 'title_name',
            'plot.x.title': 'Time (sec)',
            'plot.x.points': 'TIME',
            'plot.y.points': y_points,
            'plot.y.title': y_title,
            'plot.y2.points': y2_points,
            'plot.y2.title': y2_title,
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
        ys = self.y_criteria
        first_iter = self.tr_value['FIRST_ITER']
        last_iter = self.tr_value['LAST_ITER']
        row_data = []


        # Time response criteria will take last placed value of Y variables
        if self.criteria_mode[0]:
            row_data.append(str(self.tr_value['TR_90_%_PF']))
        if self.criteria_mode[1]:
            row_data.append(str(self.tr_value['%s_TR_%s_PF' % (ys[-1], first_iter)]))
        if self.criteria_mode[2]:
            row_data.append(str(self.tr_value['%s_TR_%s_PF' % (ys[-1], last_iter)]))

        # Default measured values are V, P and Q (F can be added) refer to set_meas_variable function
        for meas_value in self.meas_values:
            row_data.append(str(self.tr_value['%s_TR_%d' % (meas_value, last_iter)]))
            # Variables needed for variations
            if meas_value in xs:
                row_data.append(str(self.tr_value['%s_TR_TARG_%d' % (meas_value, last_iter)]))
            # Variables needed for criteria verifications with min max passfail
            if meas_value in ys:
                row_data.append(str(self.tr_value['%s_TR_TARG_%s' % (meas_value, last_iter)]))
                row_data.append(str(self.tr_value['%s_TR_%s_MIN' % (meas_value, last_iter)]))
                row_data.append(str(self.tr_value['%s_TR_%s_MAX' % (meas_value, last_iter)]))

        row_data.append(self.current_step_label)
        row_data.append(str(self.filename))
        #self.ts.log_debug(f'rowdata={row_data}')
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
        daq.data_sample()
        data = daq.data_capture_read()
        daq.sc['event'] = self.current_step_label
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
        y = self.y_criteria
        #self.tr = tr

        first_tr = self.initial_value['timestamp'] + timedelta(seconds=self.tr)
        tr_list = [first_tr]

        for i in range(self.n_tr - 1):
            tr_list.append(tr_list[i] + timedelta(seconds=self.tr))
            for meas_value in self.meas_values:
                self.tr_value['%s_TR_%s' % (meas_value, i)] = None
                if meas_value in x:
                    self.tr_value['%s_TR_TARG_%s' % (meas_value, i)] = None
                elif meas_value in y:
                    self.tr_value['%s_TR_TARG_%s' % (meas_value, i)] = None
                    self.tr_value['%s_TR_%s_MIN' % (meas_value, i)] = None
                    self.tr_value['%s_TR_%s_MAX' % (meas_value, i)] = None
        tr_iter = 1
        for tr_ in tr_list:
            #self.ts.log_debug(f'tr_={tr_list}')
            now = datetime.now()
            if now <= tr_:
                time_to_sleep = tr_ - datetime.now()
                self.ts.log('Waiting %s seconds to get the next Tr data for analysis...' %
                            time_to_sleep.total_seconds())
                self.ts.sleep(time_to_sleep.total_seconds())
            daq.data_sample()  # sample new data
            data = daq.data_capture_read()  # Return dataset created from last data capture
            daq.sc['EVENT'] = "{0}_TR_{1}".format(self.current_step_label, tr_iter)

            # update daq.sc values for Y_TARGET, Y_TARGET_MIN, and Y_TARGET_MAX

            # store the daq.sc['Y_TARGET'], daq.sc['Y_TARGET_MIN'], and daq.sc['Y_TARGET_MAX'] in tr_value

            for meas_value in self.meas_values:
                try:
                    self.tr_value['%s_TR_%s' % (meas_value, tr_iter)] = daq.sc['%s_MEAS' % meas_value]

                    self.ts.log('Value %s: %s' % (meas_value, daq.sc['%s_MEAS' % meas_value]))
                    if meas_value in x:
                        daq.sc['%s_TARGET' % meas_value] = step_value
                        self.tr_value['%s_TR_TARG_%s' % (meas_value, tr_iter)] = step_value
                        self.ts.log('X Value (%s) = %s' % (meas_value, daq.sc['%s_MEAS' % meas_value]))
                    elif meas_value in y:
                        daq.sc['%s_TARGET' % meas_value] = self.update_target_value(step_value)
                        daq.sc['%s_TARGET_MIN' % meas_value], daq.sc[
                            '%s_TARGET_MAX' % meas_value] = self.calculate_min_max_values(daq=daq, data=data)
                        self.tr_value[f'{meas_value}_TR_TARG_{tr_iter}'] = daq.sc['%s_TARGET' % meas_value]
                        self.tr_value[f'{meas_value}_TR_{tr_iter}_MIN'] = daq.sc['%s_TARGET_MIN' % meas_value]
                        self.tr_value[f'{meas_value}_TR_{tr_iter}_MAX'] = daq.sc['%s_TARGET_MAX' % meas_value]
                        self.ts.log('Y Value (%s) = %s. Pass/fail bounds = [%s, %s]' %
                                     (meas_value, daq.sc['%s_MEAS' % meas_value],
                                      daq.sc['%s_TARGET_MIN' % meas_value], daq.sc['%s_TARGET_MAX' % meas_value]))
                except Exception as e:
                    self.ts.log_debug('Measured value (%s) not recorded: %s' % (meas_value, e))

            #self.tr_value[tr_iter]["timestamp"] = tr_
            self.tr_value[f'timestamp_{tr_iter}'] = tr_
            self.tr_value['LAST_ITER'] = tr_iter
            tr_iter = tr_iter + 1

        self.tr_value['FIRST_ITER'] = 1

        return self.tr_value

        # except Exception as e:
        #    raise p1547Error('Error in get_tr_data(): %s' % (str(e)))


class CriteriaValidation:
    def __init__(self):
        self.T_min = None

    def evaluate_criterias(self, daq):
        self.response_completion_time_accuracy_criteria()
        self.transient_criteria_validation(daq)

    def transient_criteria_validation(self, daq, tr=1):

        """
           The EUT needs to begin his response to a voltage regulation demand before the response commencement time.
           Therefore, the instant that the EUT begin responding needs to be determined and this time needs to be smaller
           than 1 seconde
           Then, for the time response itself, it needs to have the good behavior. At the set time response TR1, the
           Y_TR1 is around the Open Loop Time Response value which is 90% of (Y_final - Y_initial) + y_initial

                                                                                            ------------y_final-----|
                   OLTR + Y_tol... ... ... ... ... ... ... ... ... ... ... ... ... ... .../
                   OLTR (90% * (y_final - y_initial) + y_initial) ... ... ... ... ... ..-
                   OLTR - Y_tol ... ... ... ... ... ... ... ... ... ... ... ... ... ./  |
                                                                                 -     TR1
                                                                               /
                                                                            - |
                   y2... ... ... ... ... ... ... ... ... ... ... ... ... ./Commencement tr
                                                                      -  |
                   y1 and y_initial + y_tol... ... ... ... ... ... .../    x2
                                                                 -  |
                |--y_initial-----------------------------------/    x1

                |                                              |
                tr_initial                                   beginning_time

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

             Pass/Fail criteria 1 : the Time response respect the response commencement time
             Pass If (y_initial - b)/a (beginning_time) < commencement tr
             where a = (y2-y1)/(x2-x1) and b = y1 - a*x1

             Pass/Fail cirteria 2 : The Expected value at TR1 is achieved
             OLTR = 90%*(Y_final - Y_initial) + Y_initial :
             Pass if OLTR - Y_tol <= Y_TR1 <= OLTR + Y_tol
        """
        data = daq.data_capture_dataset()
        t = data.point_data('TIME')
        for y in self.y_criteria:
            if self.T_min[y] is None:
                self.T_min[y] = 0.00

            duration = self.tr_value[f"timestamp_{tr}"] - self.initial_value['timestamp']
            duration = duration.total_seconds()
            self.ts.log(f'Calculating pass/fail for Tr = {duration} sec, with a target of {tr} sec')

            y_tol = self.s_rated * 0.04  # The tolerance of the y value = 4 % of the nominal Apparent power
            y_lim_max = self.s_rated * 1.2  # the maximum possible value for y is 120% of the nominal Apparent power
            y_lim_min = self.s_rated * -1.2  # the minimum possible value for y is -120% of the nominal Apparent power
            y_initial = self.initial_value[y]['y_value']
            y_final = self.tr_value[f'{y}_TR_TARG_{tr}']
            y_target = self.calculate_open_loop_value(y0=y_initial, y_ss=y_final, duration=duration, tr=tr)  # 90%
            y_meas = self.tr_value[f'{y}_TR_{tr}']

            if y_initial <= y_final:  # increasing values of y
                increasing = True
            else:  # decreasing values of y
                increasing = False
            # Y(time) = open loop curve, so locate the Y(time) value on the curve
            y_min = y_target - y_tol
            # Determine maximum value based on the open loop response expectation
            y_max = y_target + y_tol

            if self.phases == 'Single phase':
                y_values = data.point_data(f'AC_{y}_1')
                y_values = [y_values[i] for i in range(self.T_min[y], len(y_values) - 1)]

            elif self.phases == 'Split phase':
                y_values_1 = data.point_data(f'AC_{y}_1')
                y_values_2 = data.point_data(f'AC_{y}_2')

                y_values = [y_values_1[i] + y_values_2[i] for i in range(self.T_min[y], len(y_values_1) - 1)]

            elif self.phases == 'Three phase':
                y_values_1 = data.point_data(f'AC_{y}_1')
                y_values_2 = data.point_data(f'AC_{y}_2')
                y_values_3 = data.point_data(f'AC_{y}_3')
                y_values = [y_values_1[i] + y_values_2[i] + y_values_3[i] for i in
                            range(self.T_min, len(y_values_1) - 1)]
            j = 0
            while ((y_initial + y_tol <= y_values[j] <= y_final and y_values[j] <= y_lim_max + y_tol) and
                   increasing is True) or ((y_final <= y_values[j] <= y_initial - y_tol and
                                            y_lim_min - y_tol <= y_values[j]) and increasing is False):
                j += 1
                if j == len(y_values):
                    self.tr_value['1s_TR_PF'] = 'Fail'
                    break
            # pass/fail 1 for the commencement time
            self.T_min[y] = j
            a = (y_values[j + 1] - y_values[j]) / (t[j + 1] - t[j])
            b = y_values[j] - a * t[j]
            begin_time = (y_initial - b) / a
            # Todo: Apply this criteria to situations where the variable a is really small => not variation in Y values
            if begin_time <= self.tr_value['TR1s_TARGET']:  # Target time of the response commencement time
                self.tr_value['1s_TR_PF'] = 'Pass'
            else:
                self.tr_value['1s_TR_PF'] = 'Fail'

            # Pass/Fail 2: OLTR
            if self.increasing:
                if y_min <= y_meas:
                    self.tr_value['TR_90%_PF'] = 'Pass'
                else:
                    self.tr_value['TR_90%_PF'] = 'Fail'

                display_value_p1 = f" the beginning time [{begin_time:.3f}] <= response commencement time "
                display_value_p2 = f"[{self.tr_value['TR1s_TARGET']}:.3f] = {self.tr_value['1s_TR_PF']}"
                display_value_p3 = f"y_min_90% [{y_min:.2f}] <= y_meas [{y_meas:.2f}] = {self.tr_value['TR_90%_PF']}"
            else:  # decreasing
                if y_meas <= y_max:
                    self.tr_value['TR_90%_PF'] = 'Pass'
                else:
                    self.tr_value['TR_90%_PF'] = 'Fail'

                display_value_p1 = f" the beginning time [{begin_time:.3f}] <= response commencement time "
                display_value_p2 = f"[{self.tr_value['TR1s_TARGET']}:.3f] = {self.tr_value['1s_TR_PF']}"
                display_value_p3 = f"y_meas [{y_meas:.2f}] <= y_max_90% [{y_max:.2f}]  = {self.tr_value['TR_90%_PF']}"
            self.ts.log_debug(f'{display_value_p1} {display_value_p2} {display_value_p3}')

    def response_completion_time_accuracy_criteria(self):
        """
            Steady-State: the Eut must have linearly responded at a voltage disbalance before or equal to the response completion
            time and within the tolerance of table 2.5 and the power limitation in table 3.7 (Volt-Var) and 3.6
            (Volt-Watt)

                The variable y_tr is the value used to verify the time response requirement.
                |----------------|----------------|----------------|----------------|
                         commencement tr     completion tr   20 secondes    Commencement tr
                |                |                |
                y_initial        y_tr             y_final_tr

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

            (y_target - y_tolerance <= y_final_tr <= y_target + y_tolerance) for P and Q

        """
        for y in self.y_criteria:
            for tr_iter in range(self.tr_value['FIRST_ITER'], self.tr_value['LAST_ITER'] + 1):

                # pass/fail assessment for the steady-state values
                if self.tr_value[f'{y}_TR_{tr_iter}_MIN'] <= \
                        self.tr_value[f'{y}_TR_{tr_iter}'] <= self.tr_value[f'{y}_TR_{tr_iter}_MAX']:
                    self.tr_value[f'{y}_TR_{tr_iter}_PF'] = 'Pass'
                else:
                    self.tr_value[f'{y}_TR_{tr_iter}_PF'] = 'Fail'

                self.ts.log(f'  Steady state %s(Tr_%s) evaluation: %0.1f <= %0.1f <= %0.1f  [%s]' % (
                    y,
                    tr_iter,
                    self.tr_value[f'{y}_TR_{tr_iter}_MIN'],
                    self.tr_value[f'{y}_TR_{tr_iter}'],
                    self.tr_value[f'{y}_TR_{tr_iter}_MAX'],
                    self.tr_value[f'{y}_TR_{tr_iter}_PF']))

    def calculate_open_loop_value(self, y0, y_ss, duration, tr):
        """
        Calculated the anticipated Y(Tr +/- MRA_T) values based on duration and Tr

        Note: for a unit step response Y(t) = 1 - exp(-t/tau) where tau is the time constant

        :param y0: initial Y(0) value
        :param y_ss: steady-state solution, e.g., Y(infinity)
        :param duration: time since the change in the input parameter that the output should be calculated
        :param tr: open loop response time (90% change or 2.3 * time constant)

        :return: output Y(duration) anticipated based on the open loop response function
        """

        time_const = tr / (-(math.log(0.1)))  # ~2.3 * time constants to reach the open loop response time in seconds
        number_of_taus = duration / time_const  # number of time constants into the response
        resp_fraction = 1 - math.exp(-number_of_taus)  # fractional response after the duration, e.g. 90%

        # Y must be 90% * (Y_final - Y_initial) + Y_initial
        resp = (y_ss - y0) * resp_fraction + y0  # expand to y units

        return resp

class ImbalanceComponent:

    def __init__(self):
        self.mag = {}
        self.ang = {}

    def set_imbalance_config(self, imbalance_angle_fix=None):
        """
        Initialize the case possibility for imbalance test either with fix 120 degrees for the angle or
        with a calculated angles that would result in a null sequence zero

        :param imbalance_angle_fix:   string (Yes or No)
        if Yes, angle are fix at 120 degrees for both cases.
        if No, resulting sequence zero will be null for both cases.

        :return: None
        """

        '''
                                            Table 24 - Imbalanced Voltage Test Cases
                +-----------------------------------------------------+-----------------------------------------------+
                | Phase A (p.u.)  | Phase B (p.u.)  | Phase C (p.u.)  | In order to keep V0 magnitude                 |
                |                 |                 |                 | and angle at 0. These parameter can be used.  |
                +-----------------+-----------------+-----------------+-----------------------------------------------+
                |       Mag       |       Mag       |       Mag       | Mag   | Ang  | Mag   | Ang   | Mag   | Ang    |
        +-------+-----------------+-----------------+-----------------+-------+------+-------+-------+-------+--------+
        |Case A |     >= 1.07     |     <= 0.91     |     <= 0.91     | 1.08  | 0.0  | 0.91  |-126.59| 0.91  | 126.59 |
        +-------+-----------------+-----------------+-----------------+-------+------+-------+-------+-------+--------+
        |Case B |     <= 0.91     |     >= 1.07     |     >= 1.07     | 0.9   | 0.0  | 1.08  |-114.5 | 1.08  | 114.5  |
        +-------+-----------------+-----------------+-----------------+-------+------+-------+-------+-------+--------+

        For tests with imbalanced, three-phase voltages, the manufacturer shall state whether the EUT responds
        to individual phase voltages, or the average of the three-phase effective (RMS) values or the positive
        sequence of voltages. For EUTs that respond to individual phase voltages, the response of each
        individual phase shall be evaluated. For EUTs that response to the average of the three-phase effective
        (RMS) values mor the positive sequence of voltages, the total three-phase reactive and active power
        shall be evaluated.
        '''
        '''
        try:
            if imbalance_angle_fix == 'std':
                # Case A
                self.mag['case_a'] = [1.07 * self.v_nom, 0.91 * self.v_nom, 0.91 * self.v_nom]
                self.ang['case_a'] = [0., 120, -120]
                # Case B
                self.mag['case_b'] = [0.91 * self.v_nom, 1.07 * self.v_nom, 1.07 * self.v_nom]
                self.ang['case_b'] = [0., 120.0, -120.0]
                self.ts.log("Setting test with imbalanced test with FIXED angles/values")
            elif imbalance_angle_fix == 'fix_mag':
                # Case A
                self.mag['case_a'] = [1.07 * self.v_nom, 0.91 * self.v_nom, 0.91 * self.v_nom]
                self.ang['case_a'] = [0., 126.59, -126.59]
                # Case B
                self.mag['case_b'] = [0.91 * self.v_nom, 1.07 * self.v_nom, 1.07 * self.v_nom]
                self.ang['case_b'] = [0., 114.5, -114.5]
                self.ts.log("Setting test with imbalanced test with NOT FIXED angles/values")
            elif imbalance_angle_fix == 'fix_ang':
                # Case A
                self.mag['case_a'] = [1.08 * self.v_nom, 0.91 * self.v_nom, 0.91 * self.v_nom]
                self.ang['case_a'] = [0., 120, -120]
                # Case B
                self.mag['case_b'] = [0.9 * self.v_nom, 1.08 * self.v_nom, 1.08 * self.v_nom]
                self.ang['case_a'] = [0., 120, -120]
                self.ts.log("Setting test with imbalanced test with NOT FIXED angles/values")
            elif imbalance_angle_fix == 'not_fix':
                # Case A
                self.mag['case_a'] = [1.08 * self.v_nom, 0.91 * self.v_nom, 0.91 * self.v_nom]
                self.ang['case_a'] = [0., 126.59, -126.59]
                # Case B
                self.mag['case_b'] = [0.9 * self.v_nom, 1.08 * self.v_nom, 1.08 * self.v_nom]
                self.ang['case_b'] = [0., 114.5, -114.5]
                self.ts.log("Setting test with imbalanced test with NOT FIXED angles/values")

            #return (self.mag, self.ang)
        except Exception as e:
            self.ts.log_error('Incorrect Parameter value : %s' % e)
            raise
        '''
    def set_grid_asymmetric(self, grid, case, imbalance_resp='AVG_3PH_RMS'):
        """
        Configure the grid simulator to change the magnitude and angles.
        :param grid:   A gridsim object from the svpelab library
        :param case:   string (case_a or case_b)
        :return: nothing
        """
        self.ts.log_debug(f'mag={self.mag}')
        self.ts.log_debug(f'grid={grid}')
        self.ts.log_debug(f'imbalance_resp={imbalance_resp}')

        if grid is not None:
            grid.config_asymmetric_phase_angles(mag=self.mag[case], angle=self.ang[case])
        if imbalance_resp == 'AVG_3PH_RMS':
            self.ts.log_debug(f'mag={self.mag[case]}')
            return round(sum(self.mag[case])/3.0,2)
        elif imbalance_resp is 'INDIVIDUAL_PHASES_VOLTAGES':
            #TODO TO BE COMPLETED
            pass
        elif imbalance_resp is 'POSITIVE_SEQUENCE_VOLTAGES':
            #TODO to be completed
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

class VoltVar(EutParameters, UtilParameters, DataLogging, CriteriaValidation):
    """
    param curve: choose curve characterization [1-3] 1 is default
    """

    # Default curve initialization will be 1
    #def __init__(self, ts, imbalance=False):
    def __init__(self, ts):
        self.ts = ts
        #self.criteria_mode = [True, True, True]
        EutParameters.__init__(self, ts)
        UtilParameters.__init__(self)
        #TODO verify this section for australian standard
        DataLogging.__init__(self, meas_values=['V', 'Q', 'P'], x_criteria=['V'], y_criteria=['Q'])
        CriteriaValidation.__init__(self)
        #if imbalance:
        #    ImbalanceComponent.__init__(self)
        self.pairs = {}
        self.param = {}
        self.target_dict = []
        self.script_name = VV
        self.script_complete_name = 'Volt-Var'
        self._config()

    def _config(self):
        self.set_params()
        # Create the pairs need
        # self.set_imbalance_config()

    def set_params(self):

        self.param['Australia A'] = {
            'Vv1': round((207./230.) * self.v_nom, 2),
            'Vv2': round((220./230.) * self.v_nom, 2),
            'Vv3': round((240./230.) * self.v_nom, 2),
            'Vv4': round((258./230.) * self.v_nom, 2),
            'Q1': round(self.s_rated * 0.44, 2),
            'Q2': round(self.s_rated * 0.0, 2),
            'Q3': round(self.s_rated * 0.0, 2),
            'Q4': round(self.s_rated * -0.60, 2)
        }

        self.param['Australia B'] = {
            'Vv1': round((205./230.) * self.v_nom, 2),
            'Vv2': round((220./230.) * self.v_nom, 2),
            'Vv3': round((235./230.) * self.v_nom, 2),
            'Vv4': round((255./230.) * self.v_nom, 2),
            'Q1': round(self.s_rated * 0.3, 2),
            'Q2': round(self.s_rated * 0, 2),
            'Q3': round(self.s_rated * 0, 2),
            'Q4': round(self.s_rated * -0.4, 2)
        }

        self.param['Australia C'] = {
            'Vv1': round((215./230.) * self.v_nom, 2),
            'Vv2': round((230./230.) * self.v_nom, 2),
            'Vv3': round((240./230.) * self.v_nom, 2),
            'Vv4': round((255./230.) * self.v_nom, 2),
            'Q1': round(self.s_rated * 0.44, 2),
            'Q2': round(self.s_rated * 0, 2),
            'Q3': round(self.s_rated * 0, 2),
            'Q4': round(self.s_rated * -0.6, 2)
        }

        self.param['New Zealand'] = {
            'Vv1': round((215./230.) * self.v_nom, 2),
            'Vv2': round((230./230.) * self.v_nom, 2),
            'Vv3': round((240./230.) * self.v_nom, 2),
            'Vv4': round((255./230.) * self.v_nom, 2),
            'Q1': round(self.s_rated * 0.60, 2),
            'Q2': round(self.s_rated * 0, 2),
            'Q3': round(self.s_rated * 0, 2),
            'Q4': round(self.s_rated * -0.6, 2)
        }

    def update_target_value(self, value):

        x = [self.param[self.region]['V1'], self.param[self.region]['V2'],
             self.param[self.region]['V3'], self.param[self.region]['V4']]
        y = [self.param[self.region]['Q1'], self.param[self.region]['Q2'],
             self.param[self.region]['Q3'], self.param[self.region]['Q4']]
        q_value = float(np.interp(value, x, y))
        q_value *= self.pwr
        return round(q_value, 1)

    def calculate_min_max_values(self, daq, data):
        y = 'Q'
        v_meas = self.get_measurement_total(data=data, type_meas='V', log=False)
        target_min = self.update_target_value(v_meas + self.MRA['V'] * 1.5) - (self.MRA['Q'] * 1.5)
        target_max = self.update_target_value(v_meas - self.MRA['V'] * 1.5) + (self.MRA['Q'] * 1.5)

        return target_min, target_max

class VoltWatt(EutParameters, UtilParameters, DataLogging, CriteriaValidation):
    """
    param curve: choose curve characterization [1-3] 1 is default
    """

    # Default curve initialization will be 1
    #def __init__(self, ts, imbalance=False):
    def __init__(self, ts):
        self.ts = ts
        self.criteria_mode = [True, True, True]
        EutParameters.__init__(self, ts)
        UtilParameters.__init__(self)
        #TODO verify this section for australian standard
        DataLogging.__init__(self, meas_values=['V', 'Q', 'P'], x_criteria=['V'], y_criteria=['Q'])
        CriteriaValidation.__init__(self)
        #if imbalance:
        #    ImbalanceComponent.__init__(self)
        self.pairs = {}
        self.param = {}
        self.target_dict = []
        self.script_name = VW
        self.script_complete_name = 'Volt-Var'
        self._config()

    def _config(self):
        self.set_params()
        # Create the pairs need
        # self.set_imbalance_config()

    def set_params(self):
        self.param['Australia A'] = {
            'Vw1': round((256./230.) * self.v_nom, 2),
            'Vw2': round((260./230.) * self.v_nom, 2),
            'P1': round(1.0*self.p_rated, 2),
            'P2': round(0.2*self.p_rated, 2)
        }
        self.param['Australia B'] = {
            'Vw1': round((250./230.) * self.v_nom, 2),
            'Vw2': round((260./230.) * self.v_nom, 2),
            'P1': round(1.0*self.p_rated, 2),
            'P2': round(0.2*self.p_rated, 2)
        }
        self.param['Australia C'] = {
            'Vw1': round((253./230.) * self.v_nom, 2),
            'Vw2': round((260./230.) * self.v_nom, 2),
            'P1': round(1.0*self.p_rated, 2),
            'P2': round(0.2*self.p_rated, 2)
        }
        self.param['New Zealand'] = {
            'Vw1': round((241./230.) * self.v_nom, 2),
            'Vw2': round((246./230.)* self.v_nom, 2),
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
if __name__ == "__main__":
    pass

