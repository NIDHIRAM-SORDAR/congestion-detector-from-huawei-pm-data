import errno
import os
from pathlib import Path
from typing import Union
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.signal import find_peaks
from scipy import stats
from matplotlib.dates import DateFormatter
from matplotlib.ticker import StrMethodFormatter


def parse_raw_file(input_file):
    with open(input_file, "r", encoding="utf-8") as read_file:
        flag = True
        token = '"Resource Name"'
        BOM = "\ufeff"
        for line in read_file:
            if line.strip().startswith(token) and flag:
                yield line
                flag = False
            elif line.startswith('"') or line in ["\n"] or line.startswith(BOM):
                continue
            else:
                yield line


def clean_raw_data(input_file, out_file):
    with open(input_file, "r", encoding="utf-8") as read_file, open(out_file, "w") as write_file:
        flag = True
        token = '"Resource Name"'
        BOM = "\ufeff"
        for line in read_file:
            if line.strip().startswith(token) and flag:
                write_file.write(line)
                flag = False
            elif line.startswith('"') or line in ["\n"] or line.startswith(BOM):
                continue
            else:
                write_file.write(line)
    return out_file


def check_required_col(target, source):
    if set(target).issubset(set(source)):
        return True
    else:
        raise ValueError("Column name is inconsisted")


def prepare_dataframe(df):
    df_mod = df.copy()
    column_names = list(df_mod.columns)
    required_cols = ['Resource Name', 'Collection Time',
                     'Inbound Peak(bit/s)', 'Outbound Peak(bit/s)']
    modified_col_names = ['site_name', 'collection_time',
                          'inbound_peak_rate', 'outbound_peak_rate']
    col_names_dict = dict(zip(required_cols, modified_col_names))
    try:
        if check_required_col(required_cols, column_names):
            df_mod = df_mod[required_cols]
            df_mod.rename(columns=col_names_dict, inplace=True)

            def unit_conversion(x):
                if x[-1] == "K":
                    x = str("{:.4f}".format(float(x[:-1])/1000)) + "M"
                    return x
                else:
                    return x

            def unit_check(x):
                if str(x[-1]) not in ("M", "K"):
                    return True
                else:
                    return False
            df_mod.drop(df_mod[df_mod['inbound_peak_rate'].apply(
                unit_check)].index, inplace=True)
            df_mod.drop(df_mod[df_mod['outbound_peak_rate'].apply(
                unit_check)].index, inplace=True)

            df_mod.loc[:, 'inbound_peak_rate'] = df_mod.loc[:, 'inbound_peak_rate'].apply(
                unit_conversion)
            df_mod.loc[:, 'outbound_peak_rate'] = df_mod.loc[:, 'outbound_peak_rate'].apply(
                unit_conversion)

            df_mod.loc[:, 'site_name'] = df_mod.loc[:,
                                                    'site_name'].map(lambda x: x[:7])
            df_mod.loc[:, 'inbound_peak_rate'] = df_mod.loc[:, 'inbound_peak_rate'].map(
                lambda x: x[:-1])
            df_mod.loc[:, 'outbound_peak_rate'] = df_mod.loc[:, 'outbound_peak_rate'].map(
                lambda x: x[:-1])

            df_mod.drop(df_mod[df_mod['inbound_peak_rate']
                        == '-'].index, inplace=True)
            df_mod.drop(df_mod[df_mod['outbound_peak_rate']
                        == '-'].index, inplace=True)

            df_mod = df_mod.astype({'site_name': 'object', 'collection_time': 'datetime64',
                                    'inbound_peak_rate': 'float64', 'outbound_peak_rate': 'float64'})
            return df_mod
    except ValueError:
        raise


def plotting(data_as_time_index, site, median_of_peaks, peaks_consumption, out_folder_path):
    plt.clf()
    sns.set(font_scale=1, style='darkgrid')
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111)
    plt.title(f"{site} weekly inbound data usage")
    plt.xlabel("Day")
    plt.ylabel("Inbound Peak Rate")
    sns.lineplot(
        data=data_as_time_index['inbound_peak_rate'], color='blue', lw=1)
    sns.lineplot(data=median_of_peaks, lw=1,
                 color='red', marker="v", linestyle='--')
    sns.scatterplot(data=peaks_consumption, lw=10,
                    color='green', marker="o")
    sns.despine()

    date_form = DateFormatter("%b-%d")
    ax.xaxis.set_major_formatter(date_form)
    plt.setp(ax.get_xticklabels(), rotation=30, fontsize=10)
    fmtr = StrMethodFormatter('{x}M')
    ax.yaxis.set_major_formatter(fmtr)
    ax.legend(labels=["peak_rate", "median_peak_rate", "peaks"])
    file_name = f"{site}_PM_graph"
    file_path = out_folder_path / file_name
    yield(fig, file_path)
    plt.close()


PathLike = Union[str, Path]


def replace_ext(path: PathLike, new_ext: str = "") -> Path:
    extensions = "".join(Path(path).suffixes)
    if extensions:
        return Path(str(path).replace(extensions, new_ext))
    else:
        return path.with_suffix(new_ext)


def silentremove(filename):
    try:
        os.remove(filename)
    except OSError as e:  # this would be "except OSError, e:" before Python 2.6
        if e.errno != errno.ENOENT:  # errno.ENOENT = no such file or directory
            raise  # re-raise exception if a different error occurred
