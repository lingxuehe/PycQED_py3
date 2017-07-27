import numpy as np
from pycqed.analysis import analysis_toolbox as a_tools
import pycqed.analysis_v2.base_analysis as ba


class Single_Qubit_TimeDomainAnalysis(ba.BaseDataAnalysis):
    pass

    def process_data(self):
        '''
        This takes care of rotating and normalizing the data if required.
        this should work for several input types.
            - I/Q values (2 quadratures + cal points)
            - weight functions (1 quadrature + cal points)
            - counts (no cal points)

        There are several options possible to specify the normalization
        using the options dict.
            cal_points (tuple) of indices of the calibration points

            zero_coord, one_coord
        '''

        cal_points = self.options_dict.get('cal_points', None)
        zero_coord = self.options_dict.get('zero_coord', None)
        one_coord = self.options_dict.get('one_coord', None)

        if cal_points is None:
            # Implicit in AllXY experiments
            if len(self.data_dict['measured_values'][0]) == 42:
                cal_points = [list(range(2)), list(range(-8, -4))]
            elif len(self.data_dict['measured_values'][0]) == 21:
                cal_points = [list(range(1)), list(range(-4, -2))]
            # default for other experiments
            else:
                cal_points = [list(range(-4, -2)), list(range(-2, 0))]

        if len(self.data_dict['measured_values']) == 1:
            # if only one weight function is used rotation is not required
            self.data_dict['corr_data'] = a_tools.normalize_data_v3(
                self.data_dict['measured_values'][0],
                cal_zero_points=cal_points[0],
                cal_one_points=cal_points[1])
        else:
            self.data_dict['corr_data'], zero_coord, one_coord = \
                a_tools.rotate_and_normalize_data(
                    data=self.data_dict['measured_values'][0:2],
                    zero_coord=zero_coord,
                    one_coord=one_coord,
                    cal_zero_points=cal_points[0],
                    cal_one_points=cal_points[1])


class FlippingAnalysis(Single_Qubit_TimeDomainAnalysis):

    def __init__(self, t_start: str, t_stop: str=None,
                 options_dict: dict={}, extract_only: bool=False,
                 do_fitting: bool=True, auto=True):
        super().__init__(t_start=t_start, t_stop=t_stop,
                         options_dict=options_dict,
                         extract_only=extract_only, do_fitting=do_fitting)
        self.single_timestamp = True

        self.params_dict = {'xlabel': 'sweep_name',
                            'xunit': 'sweep_unit',
                            'sweep_points': 'sweep_points',
                            'value_names': 'value_names',
                            'value_units': 'value_units',
                            'measured_values': 'measured_values'}
        self.numeric_params = []
        if auto:
            self.run_analysis()

    def prepare_plots(self):
        self.plot_dicts['main'] = {
            'plotfn': self.plot_line,
            'xvals': self.data_dict['sweep_points'],
            'xlabel': self.data_dict['xlabel'],
            'xunit': self.data_dict['xunit'],  # does not do anything yet
            'yvals': self.data_dict['corr_data'],
            'ylabel': 'Excited state population',
            'yunit': '',
            'title': self.data_dict['timestamps'] + ' Flipping'}

    def get_scaling_factor(self):
        pass
