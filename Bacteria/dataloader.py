import os

import numpy as np
import pandas as pd

from Utils import Utils


class DataLoader:
    def preprocess_for_graphs(self, csv_path):
        df = pd.read_csv(os.path.join(os.path.dirname(__file__), csv_path), header=None)
        return self.__convert_to_numpy(df)

    def prep_process_all_data(self, csv_path):
        df = pd.read_csv(os.path.join(os.path.dirname(__file__), csv_path), header=None)
        np_covariates_X, np_treatment_Y = self.__convert_to_numpy(df)
        return np_covariates_X, np_treatment_Y

    def preprocess_data_from_csv(self, csv_path, split_size):
        # print(".. Data Loading ..")
        # data load
        df = pd.read_csv(os.path.join(os.path.dirname(__file__), csv_path), header=None)
        np_covariates_X, np_treatment_Y = self.__convert_to_numpy(df)
        # np_covariates_X = np_covariates_X / 4
        print("ps_np_covariates_X: {0}".format(np_covariates_X.shape))
        print("ps_np_treatment_Y: {0}".format(np_treatment_Y.shape))

        return np_covariates_X, np_treatment_Y

    def preprocess_data_from_csv_augmented(self, csv_path, split_size):
        # print(".. Data Loading synthetic..")
        # data load
        df = pd.read_csv(os.path.join(os.path.dirname(__file__), csv_path), header=None)
        np_covariates_X, np_treatment_Y = self.__convert_to_numpy_augmented(df)
        # print("ps_np_covariates_X: {0}".format(np_covariates_X.shape))
        # print("ps_np_treatment_Y: {0}".format(np_treatment_Y.shape))

        np_covariates_X_train, np_covariates_X_test, np_covariates_Y_train, np_covariates_Y_test = \
            Utils.test_train_split(np_covariates_X, np_treatment_Y, split_size)
        # print("np_covariates_X_train: {0}".format(np_covariates_X_train.shape))
        # print("np_covariates_Y_train: {0}".format(np_covariates_Y_train.shape))
        # print("---" * 20)
        # print("np_covariates_X_test: {0}".format(np_covariates_X_test.shape))
        # print("np_covariates_Y_test: {0}".format(np_covariates_Y_test.shape))
        return np_covariates_X_train, np_covariates_X_test, np_covariates_Y_train, np_covariates_Y_test

    @staticmethod
    def convert_to_tensor(ps_np_covariates_X, ps_np_treatment_Y):
        return Utils.convert_to_tensor(ps_np_covariates_X, ps_np_treatment_Y)

    def prepare_tensor_for_DCN(self, ps_np_covariates_X, ps_np_treatment_Y, ps_list,
                               is_synthetic):
        print(ps_np_covariates_X.shape)
        # print(ps_np_treatment_Y.shape)
        col_vector = ps_np_treatment_Y.reshape(ps_np_treatment_Y.shape[0], 1)
        print(col_vector.shape)
        X = Utils.concat_np_arr(ps_np_covariates_X,
                                col_vector,
                                axis=1)
        X = Utils.concat_np_arr(X, np.array([ps_list]).T, axis=1)
        print(X.shape)

        df_X = pd.DataFrame(X)
        treated_df_X, treated_ps_score = \
            self.__preprocess_data_for_DCN(df_X, treatment_index=1,
                                           is_synthetic=is_synthetic)

        control_df_X, control_ps_score = \
            self.__preprocess_data_for_DCN(df_X, treatment_index=0,
                                           is_synthetic=is_synthetic)

        np_treated_df_X, np_treated_ps_score = \
            self.__convert_to_numpy_DCN(treated_df_X, treated_ps_score)

        np_control_df_X, np_control_ps_score = \
            self.__convert_to_numpy_DCN(control_df_X, control_ps_score)

        print(" Treated Statistics ==>")
        print(np_treated_df_X.shape)
        print(np_treated_ps_score.shape)
        # print(np_treated_ps_score[450])

        print(" Control Statistics ==>")
        print(np_control_df_X.shape)
        print(np_control_ps_score.shape)
        # print(np_control_ps_score[200])

        return {
            "treated_data": (np_treated_df_X, np_treated_ps_score),
            "control_data": (np_control_df_X, np_control_ps_score)
        }

    @staticmethod
    def __convert_to_numpy(df):
        covariates_X = df.iloc[:, 1:]
        treatment_Y = df.iloc[:, 0]

        np_covariates_X = Utils.convert_df_to_np_arr(covariates_X)
        # print(np_covariates_X.shape)
        np_treatment_Y = Utils.convert_df_to_np_arr(treatment_Y)

        return np_covariates_X, np_treatment_Y

    @staticmethod
    def __convert_to_numpy_augmented(df):
        covariates_X = df.iloc[:, 5:]
        treatment_Y = df.iloc[:, 0:1]
        outcomes_Y = df.iloc[:, 1:3]

        np_covariates_X = Utils.convert_df_to_np_arr(covariates_X)
        np_std = np.std(np_covariates_X, axis=0)
        np_outcomes_Y = Utils.convert_df_to_np_arr(outcomes_Y)

        noise = np.empty([747, 25])
        id = -1
        for std in np_std:
            id += 1
            noise[:, id] = np.random.normal(0, 1.96 * std)

        random_correlated = np_covariates_X + noise

        random_X = np.random.permutation(np.random.random((747, 25)) * 10)
        np_covariates_X = np.concatenate((np_covariates_X, random_X), axis=1)
        np_covariates_X = np.concatenate((np_covariates_X, random_correlated), axis=1)
        np_X = Utils.concat_np_arr(np_covariates_X, np_outcomes_Y, axis=1)

        np_treatment_Y = Utils.convert_df_to_np_arr(treatment_Y)

        return np_X, np_treatment_Y

    @staticmethod
    def __preprocess_data_for_DCN(df_X, treatment_index, is_synthetic):
        # print(df_X.iloc[:, -2])

        df = df_X[df_X.iloc[:, -2] == treatment_index]

        if is_synthetic:
            # for synthetic dataset #covariates: 75
            df_X = df.iloc[:, 0:75]
        else:
            # for original dataset #covariates: 25
            df_X = df.iloc[:, 0:3198]

        ps_score = df.iloc[:, -1]

        return df_X, ps_score

    @staticmethod
    def __convert_to_numpy_DCN(df_X, ps_score):
        np_df_X = Utils.convert_df_to_np_arr(df_X)
        np_ps_score = Utils.convert_df_to_np_arr(ps_score)

        # print("np_df_X: {0}".format(np_df_X.shape))
        # print("np_ps_score: {0}".format(np_ps_score.shape))
        # print("np_df_Y_f: {0}".format(np_df_Y_f.shape))
        # print("np_df_Y_cf: {0}".format(np_df_Y_cf.shape))

        return np_df_X, np_ps_score
