import webbrowser
from kivy.lang import Builder
from kivy.properties import ObjectProperty
from kivy.properties import NumericProperty
from kivy.properties import BooleanProperty

from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.screen import MDScreen
from kivy.core.window import Window
from kivy.config import Config

from kivymd.uix.filemanager import MDFileManager
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import find_peaks
from utils import (prepare_dataframe, plotting,
                   parse_raw_file, replace_ext, silentremove)

from kivy.clock import Clock
import plyer
from kivy.garden.matplotlib import FigureCanvasKivyAgg
import matplotlib.pyplot as plt

home = str(Path.home())


Config.set('input', 'mouse', 'mouse,multitouch_on_demand')


Window.size = (720, 680)
Window.minimum_width, Window.minimum_height = Window.size
Builder.load_file('congestion_detector.kv')

KV = """
#:import FadeTransition kivy.uix.screenmanager.FadeTransition
ScreenManager:
    transition: FadeTransition()
    MainContainer:
        id: maincontainer
        name: "pm_analyzer root screen"

    GraphingScreen:
        id: graph_screen
        name: "graph screen"
"""


class GraphingScreen(ThemableBehavior, MDScreen):
    status = ObjectProperty(None)
    graph_layout = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(GraphingScreen, self).__init__(**kwargs)

    def set_text(self, text):
        self.status.text = text

    def draw_fig(self, fig):
        self.graph_layout.clear_widgets()
        self.graph_layout.add_widget(FigureCanvasKivyAgg(fig))


class MainContainer(MDScreen):
    pm_file = ObjectProperty(None)
    out_folder = ObjectProperty(None)
    pm_file_select_btn = ObjectProperty(None)
    std_value_input = ObjectProperty(None)
    save_btn = ObjectProperty(None)
    std_value = NumericProperty(2)
    message = ObjectProperty(None)
    completion_status = BooleanProperty(False)
    file_parsing_status = BooleanProperty(False)
    progress = ObjectProperty(None)
    switch = ObjectProperty(None)
    cancel_btn = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(MainContainer, self).__init__(**kwargs)
        self.manager_open = False
        self.file_manager = MDFileManager(
            exit_manager=self.exit_manager,
            select_path=self.select_path,

        )

    def file_manager_open(self, ff_type):
        # self.file_manager.show_disks()
        self.file_manager.show(home)  # output manager to the screen
        self.manager_open = True
        ext = ['.csv']
        if ff_type == 'file':
            self.file_manager.ext = ext
            self.target = self.pm_file
        else:
            self.target = self.out_folder

    def select_path(self, path):
        '''It will be called when you click on the file name
        or the catalog selection button.

        :type path: str;
        :param path: path to the selected directory or file;
        '''

        self.exit_manager()
        self.target.text = path

    def exit_manager(self, *args):
        '''Called when the user reaches the root of the directory tree.'''

        self.manager_open = False
        self.file_manager.close()

    def validate_file_type(self, instance):
        ext = ['.csv']
        str_path = instance.text
        path = Path(str_path)
        if not (path.is_file() and path.suffix in ext):
            instance.text = ""
            instance.hint_text = "Select a .csv file"
            instance.focus = True
            instance.color_active = [120/255, 166/255, 12/255, .8]
        else:
            self.pm_file_path = path

    def validate_folder_type(self, instance):
        str_path = instance.text
        path = Path(str_path)
        if not (path.is_dir() and path.exists()):
            instance.text = ""
            instance.hint_text = "Select Valid Folder"
            instance.focus = True
            instance.color_active = [120/255, 166/255, 12/255, .8]
        else:
            self.out_folder_path = path

    def set_error_message(self):
        try:
            temp_value = float(self.std_value_input.text.strip())
            if temp_value < 1 or temp_value > 3:
                self.std_value_input.error = True
            else:
                self.std_value = temp_value
        except ValueError:
            self.std_value_input.error = True

    def save_out_file(self, instance):
        filters = [("Excel file", "*.xlsx"),
                   ("Comma-separated Values", "*.csv")]
        raw_path = plyer.filechooser.save_file(filters=filters)
        try:
            raw_save_file_path = raw_path[0]
        except IndexError as e:
            return
        else:
            save_file_path = Path(raw_save_file_path)
            new_ext = ".xlsx"
            clean_path = replace_ext(save_file_path, new_ext)
            out_result = pd.DataFrame(self.result_list)
            out_result.to_excel(str(clean_path))

    def open_out_folder(self):
        try:
            path = self.out_folder_path
        except AttributeError:
            return
        else:
            webbrowser.open(path)

    def analyze_callback(self, instance):
        self.file_parsing_status = False
        self.completion_status = False
        self.progress.start()
        self.message.text = "Message"
        self.switch.disabled = True
        pm_file_path = self.pm_file_path
        try:
            self.file_generator = parse_raw_file(pm_file_path)
        except Exception as e:
            self.message.theme_text_color = "Error"
            self.message.text = str(e)
            return
        # change temp pm file name because of unknown permission error
        # not sure why it's raised yet
        temp_file = "temp_pm_file.csv"
        self.temp_clean_file_path = self.out_folder_path/temp_file
        self.file_read_event = Clock.schedule_interval(
            lambda dt: self.file_read_callback(), 0)

    def enable_cancel_btn(self):
        self.cancel_btn.disabled = False

    def delete_temp_file(self, filepath):
        try:
            silentremove(filepath)
        except Exception as e:
            pass

    def cancel_job(self):
        if self.file_read_event:
            self.file_read_event.cancel()
            self.progress.stop()
            self.delete_temp_file(self.temp_clean_file_path)
        if self.file_parsing_status == True:
            self.main_event.cancel()
        else:
            return

    def main_calculation(self):
        plt.close()
        try:
            site = next(self.df_generator)
        except StopIteration as e:
            self.message.text = "Completed!"
            MDApp.get_running_app().root.ids['graph_screen'].set_text(
                'Finished')
            self.progress.stop()
            self.completion_status = True
            self.main_event.cancel()
            self.delete_temp_file(self.temp_clean_file_path)
        else:
            result_dict = {}
            grouped_df = self.df
            data_as_time_index = grouped_df.get_group(
                site)[['collection_time', 'inbound_peak_rate']].set_index('collection_time')
            max_consumption = data_as_time_index['inbound_peak_rate'].max()
            avg_consumption = data_as_time_index['inbound_peak_rate'].mean()
            min_consumption = data_as_time_index['inbound_peak_rate'].min()
            peaks, _ = find_peaks(
                data_as_time_index['inbound_peak_rate'].values, prominence=1)
            data_as_time_index['max'] = False
            data_as_time_index.loc[data_as_time_index.iloc[peaks].index, 'max'] = True
            # Convert peaks_consumption series to df
            peaks_consumption = data_as_time_index[data_as_time_index['max']].loc[:, [
                'inbound_peak_rate']]
            # Convert median_of_peaks series to df
            median_of_peaks = data_as_time_index[data_as_time_index['max']].loc[:, ['inbound_peak_rate']].groupby(
                pd.Grouper(level=0, axis=0, freq="D")).median()  # Change mean to median
            # Drop any column with NaN bcz it will mess with z score
            median_of_peaks.dropna(inplace=True)
            # calculate zscore of median peaks
            zscore_median_peaks = np.abs(stats.zscore(
                median_of_peaks['inbound_peak_rate']))
            # drop the median peaks which zcore is greater than 2
            median_of_peaks = median_of_peaks[zscore_median_peaks <= 2]
            # as median_of_peaks is now dataframe we have to select series to list
            median_of_peaks_list = median_of_peaks['inbound_peak_rate'].tolist(
            )
            median_of_peaks_list.append(max_consumption)
            median_of_peaks_ndarray = np.array(median_of_peaks_list)
            std = np.std(median_of_peaks_ndarray)
            plt_gen = plotting(data_as_time_index, site, median_of_peaks,
                               peaks_consumption, self.out_folder_path)
            fig, file_path = next(plt_gen)
            # take account anomaly site
            # consumption is too low
            # avg_consumption taken into consideration
            if std <= self.std_value and avg_consumption >= 6:
                result_dict['Site_name'] = site
                result_dict['STD'] = std
                result_dict['Max_Consumption'] = max_consumption
                result_dict['Average_Consumption'] = avg_consumption
                result_dict['Minimum_Consumption'] = min_consumption
                result_dict['Congestion Status'] = "Congested"
                self.message.text = f"{site} is congested and Max-{max_consumption:.2f}M/Avg-{avg_consumption:.2f}M/Min-{min_consumption:.2f}M"
                fig.savefig(file_path)
            else:
                result_dict['Site_name'] = site
                result_dict['STD'] = std
                result_dict['Max_Consumption'] = max_consumption
                result_dict['Average_Consumption'] = avg_consumption
                result_dict['Minimum_Consumption'] = min_consumption
                result_dict['Congestion Status'] = "Not Congested"
                self.message.text = f"{site} is not congested and Max-{max_consumption:.2f}M/Avg-{avg_consumption:.2f}M/Min-{min_consumption:.2f}M"
            if self.switch.active:
                self.unschedule_main_calc()
                MDApp.get_running_app().root.ids['graph_screen'].set_text(
                    MDApp.get_running_app().root.ids['maincontainer'].message.text)
                MDApp.get_running_app().root.ids['graph_screen'].draw_fig(fig)

            self.result_list.append(result_dict)

    def util_generator(self):
        for site in self.df.groups.keys():
            yield site

    def set_switch_status(self):
        self.switch.active = False

    def file_read_callback(self):
        # append and read options added for bug Permission denied error
        with open(self.temp_clean_file_path, "a+") as temp_file_obj:
            try:
                line = next(self.file_generator)
                temp_file_obj.write(line)
            except StopIteration:
                self.file_parsing_status = True
                return False
            # Add finally clause as because of permission error
            # Need to investigate further
            finally:
                temp_file_obj.close()

    def schedule_main_calc(self):
        self.main_event = Clock.schedule_interval(
            lambda dt: self.main_calculation(), 1)

    def unschedule_main_calc(self):
        self.main_event.cancel()

    def on_file_parsing_status(self, instance, value):
        if self.file_parsing_status:
            self.switch.disabled = False
            try:
                df = pd.read_csv(self.temp_clean_file_path)
            except (NameError, ValueError, FileNotFoundError) as e:
                self.message.theme_text_color = "Error"
                self.message.text = str(e)
                return
            try:
                df = prepare_dataframe(df)
            except ValueError as e:
                self.message.theme_text_color = "Error"
                self.message.text = str(e)
                return
            df.to_excel(self.out_folder_path/"clean_data.xlsx")
            self.df = df.groupby('site_name')
            self.df_generator = self.util_generator()
            self.result_list = []
            self.schedule_main_calc()
        else:
            return


class PMAnalyzar(MDApp):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.accent_palette = "Gray"
        self.title = "PM Analyzer"

    def build(self):
        return Builder.load_string(KV)

    def on_stop(self):
        container_instace = MDApp.get_running_app().root.ids['maincontainer']
        if container_instace.ids._cancel_btn.disabled == False:
            container_instace.delete_temp_file(
                container_instace.temp_clean_file_path)


if __name__ == '__main__':
    PMAnalyzar().run()
