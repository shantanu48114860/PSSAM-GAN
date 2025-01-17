from collections import OrderedDict
from datetime import date

import numpy as np

from Constants import Constants
from DCN_Experiments import DCN_Experiments
from Metrics import Metrics
from PS_Manager import PS_Manager
from PS_Treated_Generator import PS_Treated_Generator
from TARNet_Experiments import TARNet_Experiments
from Utils import Utils
from dataloader import DataLoader


class Experiments:
    def __init__(self, running_mode, csv_path, split_size):
        self.dL = DataLoader()
        self.running_mode = running_mode
        self.np_train_X, self.np_train_T, self.np_train_yf, self.np_train_ycf, \
        self.np_test_X, self.np_test_T, self.np_test_yf, self.np_test_ycf, \
        self.np_val_X, self.np_val_T, self.np_val_yf, self.np_val_ycf, \
        self.np_train_mu0, self.np_test_mu0, self.np_train_mu1, self.np_test_mu1, \
        self.np_val_mu0, self.np_val_mu1 \
            = self.__load_data(csv_path, split_size)

    def run_all_experiments(self, iterations, ps_model_type):
        device = Utils.get_device()
        print(device)
        results_list = []

        run_parameters = self.__get_run_parameters()
        print(str(run_parameters["summary_file_name"]))
        file1 = open(run_parameters["summary_file_name"], "a")
        for iter_id in range(iterations):
            iter_id += 1
            print("--" * 20)
            print("iter_id: {0}".format(iter_id))
            print("IHDP Random")
            print("--" * 20)
            input_nodes = run_parameters["input_nodes"]

            # get propensity score for classifier training and testing
            ps_score_list_train, ps_score_list_val, ps_score_list_test, ps_model = \
                self.__get_ps_model(ps_model_type,
                                    iter_id,
                                    run_parameters[
                                        "input_nodes"],
                                    device)
            run_parameters["consolidated_file_path"] = self.get_consolidated_file_name(ps_model_type)
            data_loader_dict_train = self.dL.prepare_tensor_for_ITE(self.np_train_X,
                                                                    self.np_train_T,
                                                                    self.np_train_yf,
                                                                    self.np_train_ycf,
                                                                    self.np_train_mu0,
                                                                    self.np_train_mu1,
                                                                    ps_score_list_train)

            data_loader_dict_val = self.dL.prepare_tensor_for_ITE(self.np_val_X,
                                                                  self.np_val_T,
                                                                  self.np_val_yf,
                                                                  self.np_val_ycf,
                                                                  self.np_val_mu0,
                                                                  self.np_val_mu1,
                                                                  ps_score_list_val)

            data_loader_dict_test = self.dL.prepare_tensor_for_ITE(self.np_test_X,
                                                                   self.np_test_T,
                                                                   self.np_test_yf,
                                                                   self.np_test_ycf,
                                                                   self.np_test_mu0,
                                                                   self.np_test_mu1,
                                                                   ps_score_list_test)
            tensor_treated_train_original = \
                Utils.create_tensors_from_tuple(data_loader_dict_train["treated_data"])
            tensor_control_train_original = \
                Utils.create_tensors_from_tuple(data_loader_dict_train["control_data"])

            n_treated_original = data_loader_dict_train["treated_data"][0].shape[0]
            n_control_original = data_loader_dict_train["control_data"][0].shape[0]

            # Execute PM GAN
            ps_t = PS_Treated_Generator(data_loader_dict_train, data_loader_dict_val,
                                        ps_model, ps_model_type)

            balanced_dataset_dict = ps_t.simulate_treated_semi_supervised(input_nodes, iter_id, device)
            tensor_treated_balanced_dcn = balanced_dataset_dict["tensor_treated_balanced_dcn"]
            tensor_control_balanced_dcn = balanced_dataset_dict["tensor_control_balanced_dcn"]
            n_treated_balanced_dcn = balanced_dataset_dict["n_treated_balanced_dcn"]
            n_control_balanced_dcn = balanced_dataset_dict["n_control_balanced_dcn"]

            tensor_balanced_tarnet = balanced_dataset_dict["tensor_balanced_tarnet"]
            n_total_balanced_tarnet = balanced_dataset_dict["n_total_balanced_tarnet"]
            n_treated_balanced_tarnet = balanced_dataset_dict["n_treated_balanced_tarnet"]

            print("---" * 20)
            print("-----------> !! Supervised Training(DCN Models ) !!<-----------")
            # run DCN Models
            dcn_experiments = DCN_Experiments(input_nodes, device)
            dcn_pd_models_eval_dict = dcn_experiments.evaluate_DCN_Model(tensor_treated_train_original,
                                                                         tensor_control_train_original,
                                                                         n_treated_original,
                                                                         n_control_original,
                                                                         tensor_treated_balanced_dcn,
                                                                         tensor_control_balanced_dcn,
                                                                         n_treated_balanced_dcn,
                                                                         n_control_balanced_dcn,
                                                                         data_loader_dict_val,
                                                                         data_loader_dict_test)

            print("---" * 20)
            print("-----------> !! Supervised Evaluation(DCN Models) !! <-----------")
            print("---" * 20)
            print("--> 1. Model 1: DCN - PD Supervised Training Evaluation: ")
            dcn_pd_eval = dcn_pd_models_eval_dict["dcn_pd_eval_dict"]
            dcn_pd_PEHE, dcn_pd_ATE_metric, dcn_pd_true_ATE, dcn_pd_predicted_ATE = \
                self.__process_evaluated_metric(
                    dcn_pd_eval["y1_true_list"],
                    dcn_pd_eval["y0_true_list"],
                    dcn_pd_eval["y1_hat_list"],
                    dcn_pd_eval["y0_hat_list"],
                    dcn_pd_eval["ITE_dict_list"],
                    dcn_pd_eval["true_ITE"],
                    dcn_pd_eval["predicted_ITE"],
                    run_parameters["DCN_PD"],
                    iter_id)

            print("--> 2. Model 2: DCN - PD(Dropout 0.5) Supervised Training Evaluation: ")
            dcn_pd_05_eval_dict = dcn_pd_models_eval_dict["dcn_pd_05_eval_dict"]
            dcn_pd_05_PEHE, dcn_pd_05_ATE_metric, dcn_pd_05_true_ATE, dcn_pd_05_predicted_ATE = \
                self.__process_evaluated_metric(
                    dcn_pd_05_eval_dict["y1_true_list"],
                    dcn_pd_05_eval_dict["y0_true_list"],
                    dcn_pd_05_eval_dict["y1_hat_list"],
                    dcn_pd_05_eval_dict["y0_hat_list"],
                    dcn_pd_05_eval_dict["ITE_dict_list"],
                    dcn_pd_05_eval_dict["true_ITE"],
                    dcn_pd_05_eval_dict["predicted_ITE"],
                    run_parameters["DCN_PD_05"],
                    iter_id)

            print("--> 3. Model 3: PM GAN - No dropout Supervised Training Evaluation: ")
            dcn_pm_gan_eval = dcn_pd_models_eval_dict["dcn_pm_gan_eval_dict"]
            dcn_pm_gan_PEHE, dcn_pm_gan_ATE_metric, dcn_pm_gan_true_ATE, dcn_pm_gan_predicted_ATE = \
                self.__process_evaluated_metric(
                    dcn_pm_gan_eval["y1_true_list"],
                    dcn_pm_gan_eval["y0_true_list"],
                    dcn_pm_gan_eval["y1_hat_list"],
                    dcn_pm_gan_eval["y0_hat_list"],
                    dcn_pm_gan_eval["ITE_dict_list"],
                    dcn_pm_gan_eval["true_ITE"],
                    dcn_pm_gan_eval["predicted_ITE"],
                    run_parameters["DCN_PM_GAN"],
                    iter_id)

            print("--> 4. Model 4: PM GAN - dropout 0.5 Supervised Training Evaluation: ")
            dcn_pm_gan_eval_05 = dcn_pd_models_eval_dict["dcn_pm_gan_eval_drp_05_dict"]
            dcn_pm_gan_05_PEHE, dcn_pm_gan_05_ATE_metric, dcn_pm_gan_05_true_ATE, \
            dcn_pm_gan_05_predicted_ATE = \
                self.__process_evaluated_metric(
                    dcn_pm_gan_eval_05["y1_true_list"],
                    dcn_pm_gan_eval_05["y0_true_list"],
                    dcn_pm_gan_eval_05["y1_hat_list"],
                    dcn_pm_gan_eval_05["y0_hat_list"],
                    dcn_pm_gan_eval_05["ITE_dict_list"],
                    dcn_pm_gan_eval_05["true_ITE"],
                    dcn_pm_gan_eval_05["predicted_ITE"],
                    run_parameters["DCN_PM_GAN_05"],
                    iter_id)

            print("--> 5. Model 5: PM GAN - PD Supervised Training Evaluation: ")
            dcn_pm_gan_eval_pd = dcn_pd_models_eval_dict["dcn_pm_gan_eval_pd_dict"]
            dcn_pm_gan_pd_PEHE, dcn_pm_gan_pd_ATE_metric, dcn_pm_gan_pd_true_ATE, \
            dcn_pm_gan_pd_predicted_ATE = \
                self.__process_evaluated_metric(
                    dcn_pm_gan_eval_pd["y1_true_list"],
                    dcn_pm_gan_eval_pd["y0_true_list"],
                    dcn_pm_gan_eval_pd["y1_hat_list"],
                    dcn_pm_gan_eval_pd["y0_hat_list"],
                    dcn_pm_gan_eval_pd["ITE_dict_list"],
                    dcn_pm_gan_eval_pd["true_ITE"],
                    dcn_pm_gan_eval_pd["predicted_ITE"],
                    run_parameters["DCN_PM_GAN_PD"],
                    iter_id)

            print("---" * 20)

            # run TARNet Models
            tarnet_PEHE = 0
            tarnet_pm_gan_PEHE = 0
            print("-----------> !! Supervised Training(TARNet Models) !!<-----------")
            tarnet_experiments = TARNet_Experiments(input_nodes, device)
            tarnet_experiments_models_eval_dict = tarnet_experiments.evaluate_TARNet_Model(
                data_loader_dict_train["treated_data"],
                data_loader_dict_train["control_data"],
                tensor_balanced_tarnet,
                data_loader_dict_val,
                data_loader_dict_test,
                n_total_balanced_tarnet,
                n_treated_balanced_tarnet)

            tarnet_eval = tarnet_experiments_models_eval_dict["tarnet_eval_dict"]
            print("---" * 20)
            print("---> !! Supervised Evaluation(TARNet Models) !! <---")
            print("---" * 20)
            print("--> 1. Model 1: TARNet Supervised Training Evaluation: ")
            tarnet_PEHE, tarnet_ATE_metric, tarnet_true_ATE, tarnet_predicted_ATE = \
                self.__process_evaluated_metric(
                    tarnet_eval["y1_true_list"],
                    tarnet_eval["y0_true_list"],
                    tarnet_eval["y1_hat_list"],
                    tarnet_eval["y0_hat_list"],
                    tarnet_eval["ITE_dict_list"],
                    tarnet_eval["true_ITE"],
                    tarnet_eval["predicted_ITE"],
                    run_parameters["TARNET"],
                    iter_id)

            tarnet_pm_gan_eval = tarnet_experiments_models_eval_dict["tarnet_pm_gan_eval_dict"]
            print("--> 2. Model 2: TARNet PM GAN Supervised Training Evaluation: ")
            tarnet_pm_gan_PEHE, tarnet_pm_gan_ATE_metric, tarnet_pm_gan_true_ATE, \
            tarnet_pm_gan_predicted_ATE = \
                self.__process_evaluated_metric(
                    tarnet_pm_gan_eval["y1_true_list"],
                    tarnet_pm_gan_eval["y0_true_list"],
                    tarnet_pm_gan_eval["y1_hat_list"],
                    tarnet_pm_gan_eval["y0_hat_list"],
                    tarnet_pm_gan_eval["ITE_dict_list"],
                    tarnet_pm_gan_eval["true_ITE"],
                    tarnet_pm_gan_eval["predicted_ITE"],
                    run_parameters["TARNET_PM_GAN"],
                    iter_id)

            print("---" * 20)

            result_dict = OrderedDict()
            result_dict["iter_id"] = iter_id

            result_dict["PEHE_DCN_PD"] = dcn_pd_PEHE
            result_dict["ATE_Metric_DCN_PD"] = dcn_pd_ATE_metric
            result_dict["true_ATE_DCN_PD"] = dcn_pd_true_ATE
            result_dict["predicted_DCN_PD"] = dcn_pd_predicted_ATE

            result_dict["PEHE_DCN_PD_05"] = dcn_pd_05_PEHE
            result_dict["ATE_Metric_DCN_PD_05"] = dcn_pd_05_ATE_metric
            result_dict["true_ATE_DCN_PD_05"] = dcn_pd_05_true_ATE
            result_dict["predicted_DCN_PD_05"] = dcn_pd_05_predicted_ATE

            result_dict["PEHE_DCN_PM_GAN"] = dcn_pm_gan_PEHE
            result_dict["ATE_Metric_DCN_PM_GAN"] = dcn_pm_gan_ATE_metric
            result_dict["true_ATE_DCN_PM_GAN"] = dcn_pm_gan_true_ATE
            result_dict["predicted_DCN_PM_GAN"] = dcn_pm_gan_predicted_ATE

            result_dict["PEHE_DCN_PM_GAN_05"] = dcn_pm_gan_05_PEHE
            result_dict["ATE_Metric_DCN_PM_GAN_05"] = dcn_pm_gan_05_ATE_metric
            result_dict["true_ATE_DCN_PM_GAN_05"] = dcn_pm_gan_05_true_ATE
            result_dict["predicted_DCN_PM_GAN_05"] = dcn_pm_gan_05_predicted_ATE

            result_dict["PEHE_DCN_PM_GAN_PD"] = dcn_pm_gan_pd_PEHE
            result_dict["ATE_Metric_DCN_PM_GAN_PD"] = dcn_pm_gan_pd_ATE_metric
            result_dict["true_ATE_DCN_PM_GAN_PD"] = dcn_pm_gan_pd_true_ATE
            result_dict["predicted_DCN_PM_GAN_PD"] = dcn_pm_gan_pd_predicted_ATE

            result_dict["tarnet_PEHE"] = tarnet_PEHE
            result_dict["tarnet_ATE_metric"] = tarnet_ATE_metric
            result_dict["tarnet_true_ATE"] = tarnet_true_ATE
            result_dict["tarnet_predicted_ATE"] = tarnet_predicted_ATE

            result_dict["tarnet_pm_gan_PEHE"] = tarnet_pm_gan_PEHE
            result_dict["tarnet_pm_gan_ATE_metric"] = tarnet_pm_gan_ATE_metric
            result_dict["tarnet_pm_gan_true_ATE"] = tarnet_pm_gan_true_ATE
            result_dict["tarnet_pm_gan_predicted_ATE"] = tarnet_pm_gan_predicted_ATE

            file1.write("\nToday's date: {0}\n".format(date.today()))
            file1.write("Iter: {0}, PEHE_DCN_PD: {1}, "
                        "PEHE_DCN_PD(Dropout0.5): {2} "
                        "PEHE_DCN_PM_GAN: {3},  "
                        "PEHE_DCN_PM_GAN(Dropout 0.5): {4}"
                        "PEHE_DCN_PM_GAN(Dropout 0.5): {5} \n"
                        .format(iter_id,
                                dcn_pd_PEHE,
                                dcn_pd_05_PEHE,
                                dcn_pm_gan_PEHE,
                                dcn_pm_gan_05_PEHE,
                                dcn_pm_gan_pd_PEHE))
            results_list.append(result_dict)

        PEHE_set_DCN_PD = []
        ATE_Metric_set_DCN_PD = []
        true_ATE_set_DCN_PD = []
        predicted_ATE_DCN_PD = []

        PEHE_set_DCN_PD_05 = []
        ATE_Metric_set_DCN_PD_05 = []
        true_ATE_set_DCN_PD_05 = []
        predicted_ATE_DCN_PD_05 = []

        PEHE_set_DCN_PM_GAN = []
        ATE_Metric_set_DCN_PM_GAN = []
        true_ATE_set_DCN_PM_GAN = []
        predicted_ATE_DCN_PM_GAN = []

        PEHE_set_DCN_PM_GAN_05 = []
        ATE_Metric_set_DCN_PM_GAN_05 = []
        true_ATE_set_DCN_PM_GAN_05 = []
        predicted_ATE_DCN_PM_GAN_05 = []

        PEHE_set_DCN_PM_GAN_PD = []
        ATE_Metric_set_DCN_PM_GAN_PD = []
        true_ATE_set_DCN_PM_GAN_PD = []
        predicted_ATE_DCN_PM_GAN_PD = []

        PEHE_set_Tarnet = []
        ATE_Metric_set_Tarnet = []
        true_ATE_set_Tarnet = []
        predicted_ATE_Tarnet = []

        PEHE_set_Tarnet_PM_GAN = []
        ATE_Metric_set_Tarnet_PM_GAN = []
        true_ATE_set_Tarnet_PM_GAN = []
        predicted_ATE_Tarnet_PM_GAN = []

        for result in results_list:
            PEHE_set_DCN_PD.append(result["PEHE_DCN_PD"])
            ATE_Metric_set_DCN_PD.append(result["ATE_Metric_DCN_PD"])
            true_ATE_set_DCN_PD.append(result["true_ATE_DCN_PD"])
            predicted_ATE_DCN_PD.append(result["predicted_DCN_PD"])

            PEHE_set_DCN_PD_05.append(result["PEHE_DCN_PD_05"])
            ATE_Metric_set_DCN_PD_05.append(result["ATE_Metric_DCN_PD_05"])
            true_ATE_set_DCN_PD_05.append(result["true_ATE_DCN_PD_05"])
            predicted_ATE_DCN_PD_05.append(result["predicted_DCN_PD_05"])

            PEHE_set_DCN_PM_GAN.append(result["PEHE_DCN_PM_GAN"])
            ATE_Metric_set_DCN_PM_GAN.append(result["ATE_Metric_DCN_PM_GAN"])
            true_ATE_set_DCN_PM_GAN.append(result["true_ATE_DCN_PM_GAN"])
            predicted_ATE_DCN_PM_GAN.append(result["predicted_DCN_PM_GAN"])

            PEHE_set_DCN_PM_GAN_05.append(result["PEHE_DCN_PM_GAN_05"])
            ATE_Metric_set_DCN_PM_GAN_05.append(result["ATE_Metric_DCN_PM_GAN_05"])
            true_ATE_set_DCN_PM_GAN_05.append(result["true_ATE_DCN_PM_GAN_05"])
            predicted_ATE_DCN_PM_GAN_05.append(result["predicted_DCN_PM_GAN_05"])

            PEHE_set_DCN_PM_GAN_PD.append(result["PEHE_DCN_PM_GAN_PD"])
            ATE_Metric_set_DCN_PM_GAN_PD.append(result["ATE_Metric_DCN_PM_GAN_PD"])
            true_ATE_set_DCN_PM_GAN_PD.append(result["true_ATE_DCN_PM_GAN_PD"])
            predicted_ATE_DCN_PM_GAN_PD.append(result["predicted_DCN_PM_GAN_PD"])

            PEHE_set_Tarnet.append(result["tarnet_PEHE"])
            ATE_Metric_set_Tarnet.append(result["tarnet_ATE_metric"])
            true_ATE_set_Tarnet.append(result["tarnet_true_ATE"])
            predicted_ATE_Tarnet.append(result["tarnet_predicted_ATE"])

            PEHE_set_Tarnet_PM_GAN.append(result["tarnet_pm_gan_PEHE"])
            ATE_Metric_set_Tarnet_PM_GAN.append(result["tarnet_pm_gan_ATE_metric"])
            true_ATE_set_Tarnet_PM_GAN.append(result["tarnet_pm_gan_true_ATE"])
            predicted_ATE_Tarnet_PM_GAN.append(result["tarnet_pm_gan_predicted_ATE"])

        PEHE_set_DCN_PD_mean = np.mean(np.array(PEHE_set_DCN_PD))
        PEHE_set_DCN_PD_std = np.std(PEHE_set_DCN_PD)
        ATE_Metric_set_DCN_PD_mean = np.mean(np.array(ATE_Metric_set_DCN_PD))
        ATE_Metric_set_DCN_PD_std = np.std(ATE_Metric_set_DCN_PD)
        true_ATE_set_DCN_PD_mean = np.mean(np.array(true_ATE_set_DCN_PD))
        true_ATE_set_DCN_PD_std = np.std(true_ATE_set_DCN_PD)
        predicted_ATE_DCN_PD_mean = np.mean(np.array(predicted_ATE_DCN_PD))
        predicted_ATE_DCN_PD_std = np.std(predicted_ATE_DCN_PD)

        PEHE_set_DCN_PD_05_mean = np.mean(np.array(PEHE_set_DCN_PD_05))
        PEHE_set_DCN_PD_05_std = np.std(PEHE_set_DCN_PD_05)
        ATE_Metric_set_DCN_PD_05_mean = np.mean(np.array(ATE_Metric_set_DCN_PD_05))
        ATE_Metric_set_DCN_PD_05_std = np.std(ATE_Metric_set_DCN_PD_05)
        true_ATE_set_DCN_PD_05_mean = np.mean(np.array(true_ATE_set_DCN_PD_05))
        true_ATE_set_DCN_PD_05_std = np.std(true_ATE_set_DCN_PD_05)
        predicted_ATE_DCN_PD_05_mean = np.mean(np.array(predicted_ATE_DCN_PD_05))
        predicted_ATE_DCN_PD_05_std = np.std(predicted_ATE_DCN_PD_05)

        PEHE_set_DCN_PM_GAN_mean = np.mean(np.array(PEHE_set_DCN_PM_GAN))
        PEHE_set_DCN_PM_GAN_std = np.std(PEHE_set_DCN_PM_GAN)
        ATE_Metric_set_DCN_PM_GAN_mean = np.mean(np.array(ATE_Metric_set_DCN_PM_GAN))
        ATE_Metric_set_DCN_PM_GAN_std = np.std(ATE_Metric_set_DCN_PM_GAN)
        true_ATE_set_DCN_PM_GAN_mean = np.mean(np.array(true_ATE_set_DCN_PM_GAN))
        true_ATE_set_DCN_PM_GAN_std = np.std(true_ATE_set_DCN_PM_GAN)
        predicted_ATE_DCN_PM_GAN_mean = np.mean(np.array(predicted_ATE_DCN_PM_GAN))
        predicted_ATE_DCN_PM_GAN_std = np.std(predicted_ATE_DCN_PM_GAN)

        PEHE_set_DCN_PM_GAN_05_mean = np.mean(np.array(PEHE_set_DCN_PM_GAN_05))
        PEHE_set_DCN_PM_GAN_05_std = np.std(PEHE_set_DCN_PM_GAN_05)
        ATE_Metric_set_DCN_PM_GAN_05_mean = np.mean(np.array(ATE_Metric_set_DCN_PM_GAN_05))
        ATE_Metric_set_DCN_PM_GAN_05_std = np.std(ATE_Metric_set_DCN_PM_GAN_05)
        true_ATE_set_DCN_PM_GAN_05_mean = np.mean(np.array(true_ATE_set_DCN_PM_GAN_05))
        true_ATE_set_DCN_PM_GAN_05_std = np.std(true_ATE_set_DCN_PM_GAN_05)
        predicted_ATE_DCN_PM_GAN_05_mean = np.mean(np.array(predicted_ATE_DCN_PM_GAN_05))
        predicted_ATE_DCN_PM_GAN_05_std = np.std(predicted_ATE_DCN_PM_GAN_05)

        PEHE_set_DCN_PM_GAN_PD_mean = np.mean(np.array(PEHE_set_DCN_PM_GAN_PD))
        PEHE_set_DCN_PM_GAN_PD_std = np.std(PEHE_set_DCN_PM_GAN_PD)
        ATE_Metric_set_DCN_PM_GAN_PD_mean = np.mean(np.array(ATE_Metric_set_DCN_PM_GAN_PD))
        ATE_Metric_set_DCN_PM_GAN_PD_std = np.std(ATE_Metric_set_DCN_PM_GAN_PD)
        true_ATE_set_DCN_PM_GAN_PD_mean = np.mean(np.array(true_ATE_set_DCN_PM_GAN_PD))
        true_ATE_set_DCN_PM_GAN_PD_std = np.std(true_ATE_set_DCN_PM_GAN_PD)
        predicted_ATE_DCN_PM_GAN_PD_mean = np.mean(np.array(predicted_ATE_DCN_PM_GAN_PD))
        predicted_ATE_DCN_PM_GAN_PD_std = np.std(predicted_ATE_DCN_PM_GAN_PD)

        PEHE_set_Tarnet_mean = np.mean(np.array(PEHE_set_Tarnet))
        PEHE_set_Tarnet_std = np.std(PEHE_set_Tarnet)
        ATE_Metric_set_Tarnet_mean = np.mean(np.array(ATE_Metric_set_Tarnet))
        ATE_Metric_set_Tarnet_std = np.std(ATE_Metric_set_Tarnet)
        true_ATE_set_Tarnet_mean = np.mean(np.array(true_ATE_set_Tarnet))
        true_ATE_set_Tarnet_std = np.std(true_ATE_set_Tarnet)
        predicted_ATE_Tarnet_mean = np.mean(np.array(predicted_ATE_Tarnet))
        predicted_ATE_Tarnet_std = np.std(predicted_ATE_Tarnet)

        PEHE_set_Tarnet_PM_GAN_mean = np.mean(np.array(PEHE_set_Tarnet_PM_GAN))
        PEHE_set_Tarnet_PM_GAN_std = np.std(PEHE_set_Tarnet_PM_GAN)
        ATE_Metric_set_Tarnet_PM_GAN_mean = np.mean(np.array(ATE_Metric_set_Tarnet_PM_GAN))
        ATE_Metric_set_Tarnet_PM_GAN_std = np.std(ATE_Metric_set_Tarnet_PM_GAN)
        true_ATE_set_Tarnet_PM_GAN_mean = np.mean(np.array(true_ATE_set_Tarnet_PM_GAN))
        true_ATE_set_Tarnet_PM_GAN_std = np.std(true_ATE_set_Tarnet_PM_GAN)
        predicted_ATE_Tarnet_PM_GAN_mean = np.mean(np.array(predicted_ATE_Tarnet_PM_GAN))
        predicted_ATE_Tarnet_PM_GAN_std = np.std(predicted_ATE_Tarnet_PM_GAN)

        print("###" * 20)
        print("----------------- !!DCN Models(Results) !! ------------------------")
        print("--" * 20)

        print("Model 1: DCN_PD")
        print("DCN_PD, PEHE: {0}, SD: {1}"
              .format(PEHE_set_DCN_PD_mean, PEHE_set_DCN_PD_std))
        print("DCN_PD, ATE Metric: {0}, SD: {1}"
              .format(ATE_Metric_set_DCN_PD_mean, ATE_Metric_set_DCN_PD_std))
        print("DCN_PD, True ATE: {0}, SD: {1}"
              .format(true_ATE_set_DCN_PD_mean, true_ATE_set_DCN_PD_std))
        print("DCN_PD, predicted ATE: {0}, SD: {1}"
              .format(predicted_ATE_DCN_PD_mean,
                      predicted_ATE_DCN_PD_std))
        print("--" * 20)

        print("--" * 20)

        print("Model 2: DCN_PD(Dropout 0.5)")
        print("DCN_PD(Dropout 0.5), PEHE: {0}, SD: {1}"
              .format(PEHE_set_DCN_PD_05_mean, PEHE_set_DCN_PD_05_std))
        print("DCN_PD(Dropout 0.5), ATE Metric: {0}, SD: {1}"
              .format(ATE_Metric_set_DCN_PD_05_mean, ATE_Metric_set_DCN_PD_05_std))
        print("DCN_PD(Dropout 0.5), True ATE: {0}, SD: {1}"
              .format(true_ATE_set_DCN_PD_05_mean, true_ATE_set_DCN_PD_05_std))
        print("DCN_PD(Dropout 0.5), predicted ATE: {0}, SD: {1}"
              .format(predicted_ATE_DCN_PD_05_mean,
                      predicted_ATE_DCN_PD_05_std))
        print("--" * 20)

        print("Model 3: DCN PM GAN")
        print("DCN PM GAN, PEHE: {0}, SD: {1}"
              .format(PEHE_set_DCN_PM_GAN_mean, PEHE_set_DCN_PM_GAN_std))
        print("DCN PM GAN, ATE Metric: {0}, SD: {1}"
              .format(ATE_Metric_set_DCN_PM_GAN_mean, ATE_Metric_set_DCN_PM_GAN_std))
        print("DCN PM GAN, True ATE: {0}, SD: {1}"
              .format(true_ATE_set_DCN_PM_GAN_mean, true_ATE_set_DCN_PM_GAN_std))
        print("DCN PM GAN, predicted ATE: {0}, SD: {1}"
              .format(predicted_ATE_DCN_PM_GAN_mean,
                      predicted_ATE_DCN_PM_GAN_std))
        print("--" * 20)

        print("--" * 20)

        print("Model 4: DCN PM GAN Dropout 0.5")
        print("DCN PM GAN Dropout 0.5, PEHE: {0}, SD: {1}"
              .format(PEHE_set_DCN_PM_GAN_05_mean, PEHE_set_DCN_PM_GAN_05_std))
        print("DCN PM GAN Dropout 0.5, ATE Metric: {0}, SD: {1}"
              .format(ATE_Metric_set_DCN_PM_GAN_05_mean, ATE_Metric_set_DCN_PM_GAN_05_std))
        print("DCN PM GAN Dropout 0.5, True ATE: {0}, SD: {1}"
              .format(true_ATE_set_DCN_PM_GAN_05_mean, true_ATE_set_DCN_PM_GAN_05_std))
        print("DCN PM GAN Dropout 0.5, predicted ATE: {0}, SD: {1}"
              .format(predicted_ATE_DCN_PM_GAN_05_mean,
                      predicted_ATE_DCN_PM_GAN_05_std))
        print("--" * 20)

        print("Model 5: DCN PM GAN PD ")
        print("DCN PM GAN PD, PEHE: {0}, SD: {1}"
              .format(PEHE_set_DCN_PM_GAN_PD_mean, PEHE_set_DCN_PM_GAN_PD_std))
        print("DCN PM GAN PD, ATE Metric: {0}, SD: {1}"
              .format(ATE_Metric_set_DCN_PM_GAN_PD_mean, ATE_Metric_set_DCN_PM_GAN_PD_std))
        print("DCN PM GAN PD, True ATE: {0}, SD: {1}"
              .format(true_ATE_set_DCN_PM_GAN_PD_mean, true_ATE_set_DCN_PM_GAN_PD_std))
        print("DCN PM GAN PD, predicted ATE: {0}, SD: {1}"
              .format(predicted_ATE_DCN_PM_GAN_PD_mean,
                      predicted_ATE_DCN_PM_GAN_PD_std))
        print("--" * 20)

        print("###" * 20)
        print("--" * 20)
        print("----------------- !!TARNet Models(Results) !! ------------------------")
        print("--" * 20)

        print("Model 1: TARNET")
        print("TARNET, PEHE: {0}, SD: {1}"
              .format(PEHE_set_Tarnet_mean, PEHE_set_Tarnet_std))
        print("TARNET, ATE Metric: {0}, SD: {1}"
              .format(ATE_Metric_set_Tarnet_mean, ATE_Metric_set_Tarnet_std))
        print("TARNET, True ATE: {0}, SD: {1}"
              .format(true_ATE_set_Tarnet_mean, true_ATE_set_Tarnet_std))
        print("TARNET, predicted ATE: {0}, SD: {1}"
              .format(predicted_ATE_Tarnet_mean,
                      predicted_ATE_Tarnet_std))
        print("--" * 20)

        print("Model 2: TARNET PM GAN")
        print("TARNET PM GAN, PEHE: {0}, SD: {1}"
              .format(PEHE_set_Tarnet_PM_GAN_mean, PEHE_set_Tarnet_PM_GAN_std))
        print("TARNET PM GAN, ATE Metric: {0}, SD: {1}"
              .format(ATE_Metric_set_Tarnet_PM_GAN_mean, ATE_Metric_set_Tarnet_PM_GAN_std))
        print("TARNET PM GAN, True ATE: {0}, SD: {1}"
              .format(true_ATE_set_Tarnet_PM_GAN_mean, true_ATE_set_Tarnet_PM_GAN_std))
        print("TARNET PM GAN, predicted ATE: {0}, SD: {1}"
              .format(predicted_ATE_Tarnet_PM_GAN_mean,
                      predicted_ATE_Tarnet_PM_GAN_std))
        print("###" * 20)

        file1.write("\n#####################")
        file1.write("\nDCN Models")
        file1.write("\n-------------------------------")
        file1.write("\nModel 1: DCN_PD")
        file1.write("\nDCN_PD, PEHE: {0}, SD: {1}"
                    .format(PEHE_set_DCN_PD_mean, PEHE_set_DCN_PD_std))
        file1.write("\nDCN_PD, ATE Metric: {0}, SD: {1}"
                    .format(ATE_Metric_set_DCN_PD_mean,
                            ATE_Metric_set_DCN_PD_std))
        file1.write("\nDCN_PD, True ATE: {0}, SD: {1}"
                    .format(true_ATE_set_DCN_PD_mean,
                            true_ATE_set_DCN_PD_std))
        file1.write("\nDCN_PD, predicted ATE: {0}, SD: {1}"
                    .format(predicted_ATE_DCN_PD_mean,
                            predicted_ATE_DCN_PD_std))

        file1.write("\n-------------------------------")
        file1.write("\nModel 2: DCN_PD(Dropout 0.5)")
        file1.write("\nDCN_PD(Dropout 0.5), PEHE: {0}, SD: {1}"
                    .format(PEHE_set_DCN_PD_05_mean,
                            PEHE_set_DCN_PD_05_std))
        file1.write("\nDCN_PD(Dropout 0.5), ATE Metric: {0}, SD: {1}"
                    .format(ATE_Metric_set_DCN_PD_05_mean,
                            ATE_Metric_set_DCN_PD_05_std))
        file1.write("\nDCN_PD(Dropout 0.5), True ATE: {0}, SD: {1}"
                    .format(true_ATE_set_DCN_PD_05_mean,
                            true_ATE_set_DCN_PD_05_std))
        file1.write("\nDCN_PD(Dropout 0.5), predicted ATE: {0}, SD: {1}"
                    .format(predicted_ATE_DCN_PD_05_mean,
                            predicted_ATE_DCN_PD_05_std))
        file1.write("\n-------------------------------")

        file1.write("\nModel 3: DCN PM GAN")
        file1.write("\nDCN PM GAN, PEHE: {0}, SD: {1}"
                    .format(PEHE_set_DCN_PM_GAN_mean, PEHE_set_DCN_PM_GAN_std))
        file1.write("\nDCN PM GAN, ATE Metric: {0}, SD: {1}"
                    .format(ATE_Metric_set_DCN_PM_GAN_mean,
                            ATE_Metric_set_DCN_PM_GAN_std))
        file1.write("\nDCN PM GAN, True ATE: {0}, SD: {1}"
                    .format(true_ATE_set_DCN_PM_GAN_mean,
                            true_ATE_set_DCN_PM_GAN_std))
        file1.write("\nDCN PM GAN, predicted ATE: {0}, SD: {1}"
                    .format(predicted_ATE_DCN_PM_GAN_mean,
                            predicted_ATE_DCN_PM_GAN_std))
        file1.write("\n-------------------------------")

        file1.write("\nModel 4: DCN PM GAN(Dropout 0.5)")
        file1.write("\nDCN PM GAN(Dropout 0.5), PEHE: {0}, SD: {1}"
                    .format(PEHE_set_DCN_PM_GAN_05_mean,
                            PEHE_set_DCN_PM_GAN_05_std))
        file1.write("\nDCN PM GAN(Dropout 0.5), ATE Metric: {0}, SD: {1}"
                    .format(ATE_Metric_set_DCN_PM_GAN_05_mean,
                            ATE_Metric_set_DCN_PM_GAN_05_std))
        file1.write("\nDCN PM GAN(Dropout 0.5), True ATE: {0}, SD: {1}"
                    .format(true_ATE_set_DCN_PM_GAN_05_mean,
                            true_ATE_set_DCN_PM_GAN_05_std))
        file1.write("\nDCN PM GAN(Dropout 0.5), predicted ATE: {0}, SD: {1}"
                    .format(predicted_ATE_DCN_PM_GAN_05_mean,
                            predicted_ATE_DCN_PM_GAN_05_std))
        file1.write("\n-------------------------------")

        file1.write("\nModel 5: DCN PM GAN(PD")
        file1.write("\nDCN PM GAN(PD), PEHE: {0}, SD: {1}"
                    .format(PEHE_set_DCN_PM_GAN_PD_mean,
                            PEHE_set_DCN_PM_GAN_PD_std))
        file1.write("\nDCN PM GAN(PD), ATE Metric: {0}, SD: {1}"
                    .format(ATE_Metric_set_DCN_PM_GAN_PD_mean,
                            ATE_Metric_set_DCN_PM_GAN_PD_std))
        file1.write("\nDCN PM GAN(PD), True ATE: {0}, SD: {1}"
                    .format(true_ATE_set_DCN_PM_GAN_PD_mean,
                            true_ATE_set_DCN_PM_GAN_PD_std))
        file1.write("\nDCN PM GAN(PD), predicted ATE: {0}, SD: {1}"
                    .format(predicted_ATE_DCN_PM_GAN_PD_mean,
                            predicted_ATE_DCN_PM_GAN_PD_std))
        file1.write("\n-------------------------------")
        file1.write("\nModel 1: TARNET")
        file1.write("\nTARNET, PEHE: {0}, SD: {1}"
                    .format(PEHE_set_Tarnet_mean, PEHE_set_Tarnet_std))
        file1.write("\nTARNET, ATE Metric: {0}, SD: {1}"
                    .format(ATE_Metric_set_Tarnet_mean,
                            ATE_Metric_set_Tarnet_std))
        file1.write("\nTARNET, True ATE: {0}, SD: {1}"
                    .format(true_ATE_set_Tarnet_mean,
                            true_ATE_set_Tarnet_std))
        file1.write("\nTARNET, predicted ATE: {0}, SD: {1}"
                    .format(predicted_ATE_Tarnet_mean,
                            predicted_ATE_Tarnet_std))
        file1.write("\n--" * 20)
        file1.write("\nModel 2: TARNET PM GAN")
        file1.write("\nTARNET PM GAN, PEHE: {0}, SD: {1}"
                    .format(PEHE_set_Tarnet_PM_GAN_mean, PEHE_set_Tarnet_PM_GAN_std))
        file1.write("\nTARNET PM GAN, ATE Metric: {0}, SD: {1}"
                    .format(ATE_Metric_set_Tarnet_PM_GAN_mean,
                            ATE_Metric_set_Tarnet_PM_GAN_std))
        file1.write("\nTARNET PM GAN, True ATE: {0}, SD: {1}"
                    .format(true_ATE_set_Tarnet_PM_GAN_mean,
                            true_ATE_set_Tarnet_PM_GAN_std))
        file1.write("\nTARNET PM GAN, predicted ATE: {0}, SD: {1}"
                    .format(predicted_ATE_Tarnet_PM_GAN_mean,
                            predicted_ATE_Tarnet_PM_GAN_std))
        Utils.write_to_csv(run_parameters["consolidated_file_path"], results_list)

    def __get_run_parameters(self):
        run_parameters = {}
        if self.running_mode == "original_data":
            run_parameters["input_nodes"] = 25
            # run_parameters["consolidated_file_path"] = "./MSE/Results_consolidated.csv"

            # NN
            run_parameters["nn_prop_file"] = "./MSE/NN_Prop_score_{0}.csv"

            run_parameters["DCN_PD"] = "./MSE/ITE/ITE_DCN_PD_iter_{0}.csv"
            run_parameters["DCN_PD_02"] = "./MSE/ITE/ITE_DCN_PD_02_iter_{0}.csv"
            run_parameters["DCN_PD_05"] = "./MSE/ITE/ITE_DCN_PD_05_iter_{0}.csv"

            run_parameters["DCN_PM_GAN"] = "./MSE/ITE/ITE_DCN_PM_GAN_iter_{0}.csv"
            run_parameters["DCN_PM_GAN_02"] = "./MSE/ITE/ITE_DCN_PM_GAN_dropout_02_iter_{0}.csv"
            run_parameters["DCN_PM_GAN_05"] = "./MSE/ITE/ITE_DCN_PM_GAN_dropout_05_iter_{0}.csv"
            run_parameters["DCN_PM_GAN_PD"] = "./MSE/ITE/ITE_DCN_PM_GAN_dropout_PD_iter_{0}.csv"

            run_parameters["TARNET"] = "./MSE/ITE/ITE_TARNET_iter_{0}.csv"

            run_parameters["TARNET_PM_GAN"] = "./MSE/ITE/ITE_TARNET_PM_GAN_iter_{0}.csv"

            run_parameters["summary_file_name"] = "Details_original.txt"
            run_parameters["is_synthetic"] = False

        elif self.running_mode == "synthetic_data":
            run_parameters["input_nodes"] = 75
            # run_parameters["consolidated_file_path"] = "./MSE_Augmented/Results_consolidated.csv"

            run_parameters["is_synthetic"] = True

        return run_parameters

    def __load_data(self, csv_path, split_size):
        if self.running_mode == "original_data":
            return self.dL.preprocess_data_from_csv(csv_path, split_size)

        # elif self.running_mode == "synthetic_data":
        #     return self.dL.preprocess_data_from_csv_augmented(csv_path, split_size)

    def __get_ps_model(self, ps_model_type, iter_id,
                       input_nodes, device):
        ps_train_set = Utils.convert_to_tensor(self.np_train_X, self.np_train_T)
        ps_val_set = Utils.convert_to_tensor(self.np_val_X, self.np_val_T)
        ps_test_set = Utils.convert_to_tensor(self.np_test_X, self.np_test_T)
        ps_manager = PS_Manager()
        if ps_model_type == Constants.PS_MODEL_NN:
            return ps_manager.get_propensity_scores(ps_train_set,
                                                    ps_val_set,
                                                    ps_test_set, iter_id,
                                                    input_nodes, device)

        # elif ps_model_type == Constants.PS_MODEL_LR:
        #     return ps_manager.get_propensity_scores_using_LR(self.np_covariates_X_train,
        #                                                      self.np_covariates_Y_train,
        #                                                      self.np_covariates_X_val,
        #                                                      self.np_covariates_X_test,
        #                                                      regularized=False)
        # elif ps_model_type == Constants.PS_MODEL_LR_Lasso:
        #     return ps_manager.get_propensity_scores_using_LR(self.np_covariates_X_train,
        #                                                      self.np_covariates_Y_train,
        #                                                      self.np_covariates_X_val,
        #                                                      self.np_covariates_X_test,
        #                                                      regularized=True)

    @staticmethod
    def __process_evaluated_metric(y1_true, y0_true, y1_hat, y0_hat,
                                   ite_dict, true_ITE_list, predicted_ITE_list, ite_csv_path, iter_id):
        y1_true_np = np.array(y1_true)
        y0_true_np = np.array(y0_true)
        y1_hat_np = np.array(y1_hat)
        y0_hat_np = np.array(y0_hat)

        PEHE = Metrics.PEHE(y1_true_np, y0_true_np, y1_hat_np, y0_hat_np)
        ATE = Metrics.ATE(y1_true_np, y0_true_np, y1_hat_np, y0_hat_np)
        print("PEHE: {0}".format(PEHE))
        print("ATE: {0}".format(ATE))

        true_ATE = sum(true_ITE_list) / len(true_ITE_list)
        predicted_ATE = sum(predicted_ITE_list) / len(predicted_ITE_list)

        Utils.write_to_csv(ite_csv_path.format(iter_id), ite_dict)
        return PEHE, ATE, true_ATE, predicted_ATE

    def get_consolidated_file_name(self, ps_model_type):
        if ps_model_type == Constants.PS_MODEL_NN:
            return "./MSE/Results_consolidated_NN.csv"
        elif ps_model_type == Constants.PS_MODEL_LR:
            return "./MSE/Results_consolidated_LR.csv"
        elif ps_model_type == Constants.PS_MODEL_LR_Lasso:
            return "./MSE/Results_consolidated_LR_LAsso.csv"
