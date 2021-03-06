import psycopg2
import numpy as np
import base64
from Database.treatment_to_test import treatment_to_test
#from Database.sql_get_inputevents import get_inputevents
from Database.sql_get_microbiologyevents import get_microbiologyevents
from matplotlib import pyplot as plt
import icd9cms.icd9 as icd


class AntibioticsDatabase:
    def __init__(self, n_x=6, antibiotic_limit=50, seed=None):
        self.random = np.random.RandomState()
        self.random.seed(seed)
        self.antibiotic_to_treatment_dict = {}
        self.antibiotic_counter = 0
        self.n_x = n_x
        self.antibiotic_limit = antibiotic_limit
        self.organism_counter = 0
        self.organism_to_x_dict = {}
        self.n_training_samples = None
        self.antibiotics_training_data = None
        self.antibiotics_test_data = None
        self.name = 'Antibiotics'
        self.n_a = None
        self.n_y = 3
        self.max_outcome = self.n_y-1

        self.init_database()

        self.treatment_to_test = treatment_to_test
        count_working = 0
        count_not_working = 0
        for key, item in treatment_to_test.items():
            if item == None:
                count_not_working += 1
            else:
                count_working += 1
        print('Antibiotics found as both treatment and test:', count_working, ', not found:', count_not_working)
        self.allowed_tests = {'CEFTAZIDIME': True, 'PIPERACILLIN/TAZO': True, 'CEFEPIME': True,
                                   'TOBRAMYCIN': True, 'GENTAMICIN': True, 'MEROPENEM': True}
        self.allowed_organisms = {'ESCHERICHIA COLI': True, 'PSEUDOMONAS AERUGINOSA': True, 'KLEBSIELLA PNEUMONIAE': True, 'PROTEUS MIRABILIS': True}
        #self.allowed_organisms = almost_all_organisms
        for organism in self.allowed_organisms.keys():
            self.add_organism_too_dict(organism)

        for test in self.allowed_tests:
            self.add_treatment_to_dict(test)

        self.doctor_data = []

    def init_database(self):
        pw = base64.b64decode(b'aGVhbHRoeUFJ').decode("utf-8")      # Local password to postgres mimic DB
        self.conn = psycopg2.connect(database="mimic", user="postgres", password=pw)
        self.cur = self.conn.cursor()
        self.cur.execute('set search_path=mimiciii')

    def get_n_a(self):
        return min(self.antibiotic_counter, self.antibiotic_limit)

    def get_data(self):
        #self.cur.execute('SELECT hadm_id, org_name, ab_name, interpretation FROM microbiologyevents WHERE ab_name IS NOT NULL;')
        self.cur.execute(get_microbiologyevents)
        microbiology_test_data = self.cur.fetchall()

        patients = {}
        patient_age_groups = {}

        self.random.shuffle(microbiology_test_data)
        for chartevent in microbiology_test_data:
            hadm_id = chartevent[0]
            organism = chartevent[1]
            treatment_name = chartevent[2]
            outcome = interpretation_to_outcome(chartevent[3])
            age = chartevent[4]
            #age_group = chartevent[5]
            age_group = self.get_age_group_2x(age)
            treatment = self.antibiotic_to_treatment(treatment_name)
            if organism in self.allowed_organisms and treatment_name in self.allowed_tests and outcome is not None:
                intervention = np.array([treatment, outcome])
                if hadm_id in patients:
                    if organism in patients[hadm_id]:
                        if treatment not in [intervention[0] for intervention in patients[hadm_id][organism]]:
                            patients[hadm_id][organism].append(intervention)
                    else:
                        patients[hadm_id][organism] = [intervention]
                else:
                    patients[hadm_id] = {organism: [intervention]}
                    patient_age_groups[hadm_id] = age_group

        self.remove_patients(patients)

        #self.cur.execute(get_inputevents)
        #self.cur.execute("SELECT DISTINCT(label), hadm_id FROM inputevents_mv JOIN d_items ON inputevents_mv.itemid = d_items.itemid WHERE d_items.category like 'Antibiotics'")
        self.cur.execute("SELECT label, hadm_id FROM inputevents_mv JOIN d_items ON inputevents_mv.itemid = d_items.itemid "
                         "WHERE d_items.category like 'Antibiotics' order by hadm_id, starttime")

        used_antibiotics = self.cur.fetchall()
        input_patients = {}
        for chartevent in used_antibiotics:
            hadm_id = chartevent[1]

            if hadm_id in patients:
                treatment_name = self.treatment_to_test[chartevent[0]]
                treatment = self.antibiotic_to_treatment(treatment_name)
                for organism in patients[hadm_id].keys():
                    outcome = None
                    for inter in patients[hadm_id][organism]:
                        if inter[0] == treatment:
                            outcome = inter[1]
                    if outcome is not None:
                        intervention = np.array([treatment, outcome])
                        if hadm_id in input_patients:
                            if organism in input_patients[hadm_id]:
                                treatments = [intervention[0] for intervention in input_patients[hadm_id][organism]]
                                if treatment not in treatments:
                                    input_patients[hadm_id][organism].append(intervention)
                            else:
                                input_patients[hadm_id][organism] = [intervention]
                        else:
                            input_patients[hadm_id] = {organism: [intervention]}

        input_patients = self.remove_input_patients(input_patients)
        #self.remove_training_data_from_test(input_patients, patients)
        input_patients, patients = self.split_training_to_test(input_patients, patients)

        self.n_a = len(self.allowed_tests.keys())

        #self.plot_outcome_histogram(microbiology_test_data)
        #self.plot_matrix(microbiology_test_data)

        self.comorbidites = self.load_comorbidities()


        antibiotics_data = {'z': [], 'x': [], 'h': []}
        test_data = []

        for hadm_id, microbiology_test_data in patients.items():
            for organism, history in microbiology_test_data.items():
                organism_x = self.organism_to_x_dict[organism]
                age_group = patient_age_groups[hadm_id]
                comorbities = self.get_comorbidites_x(hadm_id)
                x = self.create_x((organism_x, age_group, comorbities))
                test_data.append(self.get_test_data(x, history))

        for hadm_id, organism_and_history in input_patients.items():
            for organism, history in organism_and_history.items():
                organism_x = self.organism_to_x_dict[organism]
                age_group = patient_age_groups[hadm_id]
                comorbities = self.get_comorbidites_x(hadm_id)
                x = self.create_x((organism_x, age_group, comorbities))
                antibiotics_data['z'].append(hadm_id)
                antibiotics_data['x'].append(x)
                antibiotics_data['h'].append(history)


        print("{} different antibiotics".format(self.n_a))
        self.antibiotics_training_data = antibiotics_data
        print("{} patients in training data, {} in test data".format(len(antibiotics_data['x']), len(test_data)))
        print("{} organisms".format(self.organism_counter))
        print("Organisms: {}".format(list(self.organism_to_x_dict.keys())))
        return antibiotics_data, test_data

    def get_age_group_2x(self, age):
        if age > 60:
            return self.int_to_binary(3, 2)
        elif 60 >= age > 31:
            return self.int_to_binary(2, 2)
        elif 31 >= age > 15:
            return self.int_to_binary(1, 2)
        elif 15 >= age >= 0:
            return self.int_to_binary(0, 2)

    def load_comorbidities(self):
        comorbidities = {}
        self.cur.execute("SELECT hadm_id, icd9_code FROM diagnoses_icd")
        diagnoses = self.cur.fetchall()
        for chartevent in diagnoses:
            hadm_id = chartevent[0]
            icd9 = chartevent[1]
            if hadm_id in comorbidities:
                comorbidities[hadm_id].append(icd9)
            else:
                comorbidities[hadm_id] = [icd9]
        return comorbidities

    def get_comorbidites_x(self, hadm_id):
        comorbidities = self.comorbidites[hadm_id]
        comorbidities_x = [0, 0]
        for comorbidity_code in comorbidities:
            info = icd.search(comorbidity_code)
            while info is not None:
                description = info.short_desc
                if description == 'Infectious And Parasitic Diseases':
                    comorbidities_x[0] = 1
                    break
                elif description == 'Diseases Of The Skin And Subcutaneous Tissue':
                    comorbidities_x[1] = 1
                    break
                else:
                    info = info.parent
        return comorbidities_x

    def create_x(self, args):
        x = np.concatenate(args)
        return x

    def split_training_to_test(self, training, test, split=0.7):
        hadm_ids = np.array(list(training.keys()))
        training_samples = int(np.ceil(len(hadm_ids)*split))
        test_samples = int(np.floor(len(hadm_ids)*(1 - split)))
        tr_s = [True]*training_samples
        te_s = [False]*test_samples
        is_training_sample = tr_s + te_s
        print(len(is_training_sample), len(training))
        self.random.shuffle(is_training_sample)
        test_set = {}
        training_set = {}
        i = 0
        for hadm_id, organism_and_history in training.items():
            #print(i, len(training))
            if is_training_sample[i]:
                training_set[hadm_id] = organism_and_history
            else:
                test_set[hadm_id] = organism_and_history
            i += 1

        doctor_data = {'z': [], 'x': [], 'h': []}
        for hadm_id, organism_and_history in test_set.items():
            for organism, history in organism_and_history.items():
                doctor_data['h'].append(history)
        self.doctor_data = doctor_data

        new_test_set = {}
        test_hadm_ids = np.ma.masked_array(hadm_ids, mask=is_training_sample)
        test_hadm_ids = test_hadm_ids[test_hadm_ids.mask == False]
        for hadm_id in test_hadm_ids:
            new_test_set[hadm_id] = test[hadm_id]
        return training_set, new_test_set

    def remove_training_data_from_test(self, training, test):
        for hadm_id in training.keys():
            if hadm_id in test:
                del test[hadm_id]

    def remove_patients(self, patients):
        allowed_treatments_list = list(self.allowed_tests.keys())
        patients_to_delete = []
        for hadm_id, organism in patients.items():
            for organism, history in organism.items():
                for treatment in allowed_treatments_list:
                    if self.antibiotic_to_treatment_dict[treatment] not in [intervention[0] for intervention in history]:
                        patients_to_delete.append([hadm_id, organism])
                        break
        print(len(patients_to_delete), 'patients to delete')
        for patient in patients_to_delete:
            hadm_id = patient[0]
            organism = patient[1]
            if hadm_id in patients:
                if organism in patients[hadm_id]:
                    del patients[hadm_id][organism]

    def remove_input_patients(self, patients):
        allowed_treatments_list = list(self.allowed_tests.keys())
        patients_to_delete = []
        for hadm_id, organism in patients.items():
            for org, history in organism.items():
                used_treatments = [intervention[0] for intervention in history]
                for used_treatment in used_treatments:
                    if used_treatment not in [self.antibiotic_to_treatment_dict[t] for t in allowed_treatments_list]:
                        patients_to_delete.append(hadm_id)
                        break

        for hadm_id in patients_to_delete:
            del patients[hadm_id]
        return patients

    def get_organisms_and_outcomes(self, data):
        organisms_and_outcome = {}
        for chartevent in data:
            hadm_id = chartevent[0]
            organism = chartevent[1]
            treatment_name = chartevent[2]
            treatment = self.antibiotic_to_treatment(treatment_name)
            outcome = interpretation_to_outcome(chartevent[3])
            if outcome is not None:
                if treatment in organisms_and_outcome:
                    if organism in organisms_and_outcome[treatment]:
                        organisms_and_outcome[treatment][organism].append(outcome)
                    else:
                        organisms_and_outcome[treatment][organism] = [outcome]
                else:
                    organisms_and_outcome[treatment] = {}
        return organisms_and_outcome

    def plot_outcome_histogram(self, data):
        organisms_and_outcome = self.get_organisms_and_outcomes(data)
        valid_treatments = self.get_valid_treatments()
        colors = self.get_x_colors()

        for treatment, organism_outcome in organisms_and_outcome.items():
            outcomes = []
            organism_colors = []
            organisms_labels = []
            for organism, outcome in organism_outcome.items():
                outcome = [(o*0.3)+treatment for o in outcome]
                outcomes.append(np.array(outcome))
                organism_colors.append(colors[self.binary_to_int(self.organism_to_x_dict[organism])])
                organisms_labels.append(organism)
            plt.hist(outcomes, bins=3, stacked=True, color=organism_colors)
        plt.xticks(np.arange(len(valid_treatments)), valid_treatments, rotation='vertical', fontsize=7)
        plt.show()

    def plot_matrix(self, data):
        organisms_and_treatments = np.zeros((self.n_a, self.n_a))

        for chartevent in data:
            #hadm_id = chartevent[0]
            organism = chartevent[1]
            treatment_name = chartevent[2]
            treatment = self.antibiotic_to_treatment(treatment_name)
            #outcome = interpretation_to_outcome(chartevent[3])
            if organism not in self.organism_to_x_dict:
                self.add_organism_too_dict(organism)
            organism_id = self.binary_to_int(self.organism_to_x_dict[organism])
            if organism_id < self.n_a:
                organisms_and_treatments[treatment, organism_id] += 1

        fig = plt.figure()
        ax = fig.add_subplot(111)
        cax = ax.matshow(organisms_and_treatments, cmap=plt.get_cmap('jet'))
        fig.colorbar(cax)
        ax.set_xlabel('Organisms')
        ax.set_ylabel('Treatments')

        plt.show()

    def get_x_colors(self):
        colors = []
        cmap = plt.get_cmap('gist_ncar')
        color_steps = np.linspace(0, 1, self.organism_counter)
        for i in color_steps:
            colors.append(cmap(i))
        return colors

    def get_valid_treatments(self):
        valid_treatments = []
        for treatment, test in self.treatment_to_test.items():
            if test is not None:
                valid_treatments.append(treatment)
        return valid_treatments

    def binary_to_int(self, binary):
        return int("".join(str(i) for i in binary), 2)

    def antibiotic_to_treatment(self, antibiotic):
        if antibiotic in self.antibiotic_to_treatment_dict:
            index = self.antibiotic_to_treatment_dict[antibiotic]
        else:
            index = self.antibiotic_counter
            self.antibiotic_to_treatment_dict[antibiotic] = index
            self.antibiotic_counter += 1
        return index

    def add_treatment_to_dict(self, treatment):
        if treatment not in self.antibiotic_to_treatment_dict:
            index = self.antibiotic_counter
            self.antibiotic_to_treatment_dict[treatment] = index
            self.antibiotic_counter += 1

    def add_organism_too_dict(self, organism):
        if organism not in self.organism_to_x_dict:
            length = int(np.ceil(np.sqrt(len(self.allowed_organisms))))
            binary = self.int_to_binary(self.organism_counter, length)
            self.organism_to_x_dict[organism] = binary
            self.organism_counter += 1

    def int_to_binary(self, integer, length):
        conversion = '{}0:0{}b{}'.format('{', str(length), '}')
        binary = np.array(
            [int(s) for s in list((conversion.format(integer)))])  # Convert to list of binary
        return binary

    def get_test_data(self, x, history):
        z = -1
        subject = [z, x, np.ones(self.n_a)*-1]

        for intervention in history:
            treatment, outcome = intervention

            subject[2][treatment] = outcome
        return subject

    def shuffle_histories(self, xs, histories):
        patients = list(zip(xs, histories))
        self.random.shuffle(patients)
        xs, histories = zip(*patients)
        return xs, histories


def interpretation_to_outcome(interpretation):
    if interpretation == 'S':
        return 2
    elif interpretation == 'I':
        return 1
    elif interpretation == 'R':
        return 0
    elif interpretation == 'P':
        return None



