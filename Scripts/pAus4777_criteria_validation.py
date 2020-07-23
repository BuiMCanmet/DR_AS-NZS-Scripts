class CriteriaValidation:
    def __init__(self):

    def evaluate_criterias(self):
        self.response_commencement_time_criteria()
        self.response_completion_time_accuracy_criteria()

    def response_commencement_time_criteria(self, tr=1):
        """
                TRANSIENT: the Eut must begin to respond at a voltage disbalance before the response commencement time

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

                    y_tr != y_initial
        """

        y = self.y_criteria[0]

        duration = self.tr_value[f"timestamp_{tr}"] - self.initial_value['timestamp']
        duration = duration.total_seconds()
        self.ts.log(f'Calculating pass/fail for Tr = {duration} sec, with a target of {tr} sec')

        # Given that Y(time) is defined by an open loop response characteristic, use that curve to
        # calculated the target, minimum, and max, based on the open loop response expectation
        y_start = self.initial_value[y]['y_value']
        y_ss = self.tr_value[f'{y}_TR_TARG_{tr}']
        y_meas = self.tr_value[f'{y}_TR_{tr}']
        self.ts.log_debug(f'y_start = {y_start}, y_commmencement_tr = {y_meas}')

        if y_start <= y_ss:  # increasing values of y
            increasing = True
        else:  # decreasing values of y
            increasing = False

        # Pass/Fail: Y_start <= Ymeas <= Y_ss
        if increasing:
            if y_start <= y_meas <= y_ss:
                self.tr_value['TR_COMMENCEMENT_PF'] = 'Pass'
            else:
                self.tr_value['TR_COMMENCEMENT_PF'] = 'Fail'

            display_value_p1 = f'y_min [{y_start:.2f}] <= y_meas'
            display_value_p2 = f'[{y_meas:.2f}] <= y_max [{y_ss:.2f}] = {self.tr_value["TR_COMMENCEMENT_PF"]}'
        else:
            if y_ss <= y_meas <= y_start:
                self.tr_value['TR_COMMENCEMENT_PF'] = 'Pass'
            else:
                self.tr_value['TR_COMMENCEMENT_PF'] = 'Fail'

            display_value_p1 = f'y_min [{y_ss:.2f}] <= y_meas'
            display_value_p2 = f'[{y_meas:.2f}] <= y_max [{y_start:.2f}] = {self.tr_value["TR_COMMENCEMENT_PF"]}'
        self.ts.log_debug(f'{display_value_p1} {display_value_p2}')


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
            for tr_iter in range(self.tr_value['FIRST_ITER'], self.tr_value['LAST_ITER']+1):

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