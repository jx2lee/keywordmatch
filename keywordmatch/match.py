from datetime import datetime
from tqdm import tqdm
import flashtext
import jaydebeapi
import logging
import os
import pandas as pd


class MatchingProcessor(object):
    """MatchingProcessor Class
        Keyword Matching Using flashtext

    """

    def __init__(self, data, input_column, output_columns):
        """
        Args:
            data : pd.DataFrame
                DataFrame that you want to match keyword
            input_column : string
                String about column name of DataFrame
            output_columns : list
                List about column what you want to match

        """
        self._data = data
        self._input_column = input_column
        self._keyword_dict = {}
        self._keyword_processor = flashtext.KeywordProcessor()
        self._logger = logging.getLogger()
        self._output_columns = output_columns

        # Check Variable type
        if type(self._data) != pd.DataFrame:
            raise TypeError(f'You must set data is pd.DataFrame. current type is {type(self._data)}')
        if type(self._input_column) != str:
            raise TypeError(f'You must set input_column is str. current type is {type(self._input_column)}')
        if type(self._output_columns) != list:
            raise TypeError(f'You must set output_columns is list. current type is {type(self._output_columns)}')

    def set_logger(self, logfile_name, is_file=True):
        """To set logger

        Args:
            logfile_name : string
                word that you want to set logfile name

            is_file : bool
                If you want to get File, Set True

        """
        # Check Logger handler exists
        if len(self._logger.handlers) >= 2:
            return None

        self._logger.setLevel(logging.INFO)
        formatter = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s")
        file_max_bytes = 10 * 1024 * 1024

        # set StreamHandler
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        self._logger.addHandler(stream_handler)

        # set RotatingFileHandler
        if is_file:
            rotating_file_handler = logging.handlers.RotatingFileHandler(
                filename=os.getcwd() + "/" + logfile_name + ".log",
                maxBytes=file_max_bytes,
                backupCount=2)
            rotating_file_handler.setFormatter(formatter)
            self._logger.addHandler(rotating_file_handler)

    def add_column(self):
        """To Add columns for matching keyword
        """
        for col in self._output_columns:
            self._data[col] = 0
        self._logger.info(f'Finished Adding Columns: {self._output_columns}')

    def get_keyword_processor(self, data, key, value):
        """To get keyword_processor using FlashText

        Args:
            data : pd.DataFrame
                DataFrame with keywords (master table)

            key : string
                DataFrame Column for Keyword type

            value : string
                DataFrame Column for Keyword value

        """
        for col in self._output_columns:
            self._keyword_dict[col] = data[data[key] == col][value].to_list()

        self._keyword_processor.add_keywords_from_dict(self._keyword_dict)
        self._logger.info(f'Finished Setting Keyword_processor: {self._keyword_processor.get_all_keywords()}')

    def is_keyword(self):
        """Match keyword about added column

        Returns:
            data : pd.DataFrame
                DataFrame after keyword matching

        """
        self._logger.info('Start Keyword Match.')
        for i in tqdm(self._data.index):
            text = self._data.at[i, self._input_column]
            extract_keywords = set(self._keyword_processor.extract_keywords(text))
            for keyword in self._output_columns:
                if keyword in extract_keywords:
                    self._data.at[i, keyword] = 1
        self._logger.info(f'Finished Keyword Match.')
        return self._data

    def save_output_file(self, file_name):
        """To save DataFrame as file

        Args:
            file_name : string

        """
        self._data.to_csv(os.getcwd() + '/' + file_name, mode=a, header=True)
        self._logger.info(f'Saved file {file_name} in {os.getcwd()}')

    def save_output_database(self, jar_file, db_info):
        """To save DataFrame in Tibero

        Args:
            jar_file : string
                jar file path for Tibero connection

            db_info : dictionary
                info for Tibero Connection. For example:
                *ip/port/sid(str)       : ip address/port/sid for Tibero
                *id_pw(str)             : User ID/Password
                *table(str)             : Table to be loaded
                *table_columns(list)    : Columns to save
                *output_columns(list)   : Columns to be extracted from the data frame

        Examples:
            >>> db = {"ip" : "192.168.179.166", 'sid':'tibero', "id_pw":['tibero', 'tmax'],
            'output_columns':['기사제목','기사내용','수집시간'], 'table': 'CRAWLER_DATA',
            'table_columns':['DETECTED_LINK', 'DETECTED_CONTENTS', 'DETECTED_TIME']}
            >>> instance.save_output_database(jar_file='{your_jar_file_path}/tibero6-jdbc.jar', db_info=db)

        """
        # Check jar file
        if not os.path.isfile(jar_file):
            raise IOError(f'Invalid file path {jar_file}')

        # Database Connection
        conn = jaydebeapi.connect('com.tmax.tibero.jdbc.TbDriver',
                                  f'jdbc:tibero:thin:@{db_info["ip"]}:{db_info["port"]}:{db_info["sid"]}',
                                  db_info['id_pw'],
                                  jar_file)
        self._logger.info(f'Connected Tibero: {db_info["ip"]}:{db_info["port"]}:{db_info["sid"]}')

        # Create cursor and insert data during Loop
        dump = []
        self._logger.info(f'Started Creating SQL dump.')
        for i in tqdm(self._data.index):
            dump.append(list(self._data.at[i, col] for col in db_info['output_columns']))
        self._logger.info(f'Finished Creating SQL dump. dump size: {len(dump)}')

        # Set Cursor and Put dump
        cursor = conn.cursor()
        insert_query = f'INSERT INTO {db_info["table"]} VALUES ({",".join(str("?") for i in range(len(db_info["table_columns"])))})'

        self._logger.info(f'Started pushing data. SQL Query: {insert_query}')
        if len(dump) > 1:
            cursor.executemany(insert_query, dump)
        else:
            cursor.execute(insert_query, dump)
        self._logger.info(f'Finished pushing data.')

        # Disconnect Database
        cursor.close
        conn.close
        self._logger.info(f'Disconnected Tibero.')