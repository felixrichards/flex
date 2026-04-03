from . import constants
from . import myresources

from typing import List


class Filter():
    filter_strs_to_filters = {}
    filter_to_champ = {}

    def __init__(self):
        self.filters = []

    @classmethod
    def get_valid_filters(cls):
        return list(cls.filter_strs_to_filters.keys())

    @classmethod
    def is_valid(self, filter_str: str):
        return self.process_filter_str(filter_str) in self.filter_strs_to_filters.keys()

    @staticmethod
    def process_filter_str(x):
        return x.upper()
    
    def add(self, filter_str: str):
        filter_str = self.process_filter_str(filter_str)
        if not self.is_valid(filter_str):
            raise ValueError(f"Given filter string {filter_str} is not valid")
        actual_filter = self.filter_strs_to_filters[filter_str]
        if actual_filter not in self.filters:
            self.filters.append(actual_filter)
    
    def filter(self, champs):
        if not self.filters:
            return champs

        filtered_champs = []
        for actual_filter in self.filters:
            possible_champs = self.filter_to_champ[actual_filter]
            for champ in champs:
                if champ in possible_champs and champ not in filtered_champs:
                    filtered_champs.append(champ)
        return filtered_champs

class RoleFilter(Filter):
    filter_strs_to_filters = {
        **{role: role for role in constants.ROLES},
        **{f"{role}S": role for role in constants.ROLES},
        "MIDDLE": constants.MID,
        "MIDDLES": constants.MID,
        "ADC": constants.BOT,
        "ADCS": constants.BOT,
        "APC": constants.BOT,
        "APCS": constants.BOT,
        "BOTTOM": constants.BOT,
        "BOTTOMS": constants.BOT,
        "JG": constants.JUNGLE,
        "JGS": constants.JUNGLE,
        "JGL": constants.JUNGLE,
        "JGLS": constants.JUNGLE,
        "SUPPORT": constants.SUPP,
        "SUPPORTS": constants.SUPP,
    }

    filter_to_champ = myresources.CHAMPS_BY_ROLE

    @staticmethod
    def process_filter_str(x):
        return x.upper()
            
    
class ClassFilter(Filter):
    filter_strs_to_filters = {
        **{league_class: league_class for league_class in constants.CLASSES},
        **{f"{league_class}s": league_class for league_class in constants.CLASSES}
    }

    filter_to_champ = myresources.CHAMPS_BY_CLASS

    @staticmethod
    def process_filter_str(x: str):
        return x.capitalize()


class DamageTypeFilter(Filter):
    filter_strs_to_filters = {
        **{dmg_type: dmg_type for dmg_type in constants.DAMAGE_TYPES},
        **{f"{dmg_type}S": dmg_type for dmg_type in constants.DAMAGE_TYPES},
        "ADC": constants.AD_DAMAGE_TYPE,
        "ADCS": constants.AD_DAMAGE_TYPE,
        "APC": constants.AP_DAMAGE_TYPE,
        "APCS": constants.AP_DAMAGE_TYPE,
    }

    filter_to_champ = myresources.CHAMPS_BY_DAMAGE_TYPE

    @staticmethod
    def process_filter_str(x: str):
        return x.upper()


class GenderFilter(Filter):
    filter_strs_to_filters = {
        "MALE": "MALE",
        "M": "MALE",
        "MEN": "MALE",
        "MAN": "MALE",
        "BOY": "MALE",
        "LAD": "MALE",
        "GENT": "MALE",
        "GENTELMAN": "MALE",
        "GENTELMEN": "MALE",
        "DUDE": "MALE",
        "BRO": "MALE",
        "FEMALE": "FEMALE", 
        "F": "FEMALE",
        "WOMEN": "FEMALE",
        "WOMAN": "FEMALE",
        "LADY": "FEMALE",
        "LADIES": "FEMALE",
        "GAL": "FEMALE",
        "GIRL": "FEMALE",
        "OTHER": "OTHER",
        "NONBINARY": "OTHER",
        "NON-BINARY": "OTHER",
        "UNKNOWN": "OTHER",
        "AGENDER": "OTHER",
        "AMBIGUOUS": "OTHER",
        "NONE": "OTHER",
        "THEY": "OTHER",
        "THEM": "OTHER",
        "THEIR": "OTHER",
        "NEUTRAL": "OTHER",
    }

    filter_to_champ = myresources.CHAMPS_BY_GENDER

    def __init__(self):
        self.filter_strs_to_filters.update(
            {f"{s}S": v for s, v in self.filter_strs_to_filters.items()}
        )
        super().__init__()

    @staticmethod
    def process_filter_str(x: str):
        return x.upper()


class LgbtFilter(Filter):
    filter_strs_to_filters = {
        "LGBT": "LGBT",
        "QUEER": "LGBT",
        "GAY": "LGBT",
        "STRAIGHT": "NONLGBT",
        "NONLGBT": "NONLGBT",
        "LGBTS": "LGBT",
        "QUEERS": "LGBT",
        "GAYS": "LGBT",
        "STRAIGHTS": "NONLGBT",
        "NONLGBTS": "NONLGBT",
    }

    filter_to_champ = myresources.CHAMPS_BY_LGBT

    @staticmethod
    def process_filter_str(x: str):
        return x.upper()


class ComplexionFilter(Filter):
    filter_strs_to_filters = {
        "OTHER": "0",
        "WHITE": "1",
        "CHOCCY": "2",
        "CHOC": "2",
        "CHOCOLATE": "2",
        "BLACK": "3",
    }

    filter_to_champ = myresources.CHAMPS_BY_COMPLEXION

    def __init__(self):
        self.filter_strs_to_filters.update(
            {f"{s}S": v for s, v in self.filter_strs_to_filters.items()}
        )
        super().__init__()

    @staticmethod
    def process_filter_str(x: str):
        return x.upper()


def parse_filters(filter_strs):
    filter_objs: List[Filter] = [RoleFilter(), ClassFilter(), DamageTypeFilter(), GenderFilter(), LgbtFilter(), ComplexionFilter()]
    for filter_obj in filter_objs:
        for filter_str in filter_strs:
            if filter_obj.is_valid(filter_str):
                filter_obj.add(filter_str)
    return filter_objs

def is_valid_filter(filter_str):
    filter_classes = [RoleFilter, ClassFilter, DamageTypeFilter, GenderFilter(), LgbtFilter, ComplexionFilter()]
    for filter_class in filter_classes:
        if filter_class.is_valid(filter_str):
            return True
    return False
