import glob
import os
import json
import yaml
from PIL import Image

RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))


CHAMPS_PLAYERS_MANIFEST_FILENAME = "champs_players_manifest.json"
with open(os.path.join(RESOURCE_DIR, CHAMPS_PLAYERS_MANIFEST_FILENAME), "r") as f:
    CHAMPS_PLAYERS_MANIFEST = json.load(f)

PLAYER_TO_NAME_FILENAME = "player_to_name.json"
with open(os.path.join(RESOURCE_DIR, PLAYER_TO_NAME_FILENAME), "r") as f:
    PLAYER_TO_NAME = json.load(f)


CHAMP_DATA_DB_FILENAME = "champ_data_db.yaml"
with open(os.path.join(RESOURCE_DIR, CHAMP_DATA_DB_FILENAME), "r") as f:
    _champ_data_db = yaml.safe_load(f)

_champions = _champ_data_db["champions"]
_role_order = ["TOP", "JUNGLE", "MID", "BOT", "SUPP"]

CHAMPS_WITH_ROLE_DATA = []
for champion in _champions:
    flags = [role if role in champion["roles"] else "" for role in _role_order]
    CHAMPS_WITH_ROLE_DATA.append("\t".join([champion["name"], *flags, ""]))

ROLES_BY_CHAMP = {champion["name"]: champion["roles"] for champion in _champions}

CHAMPS_BY_ROLE = {}
for role in _role_order:
    CHAMPS_BY_ROLE[role] = [champion["name"] for champion in _champions if role in champion["roles"]]

CHAMPS_BY_DAMAGE_TYPE = {}
for champion in _champions:
    for damage_type in champion["damage"]:
        CHAMPS_BY_DAMAGE_TYPE.setdefault(damage_type, []).append(champion["name"])


CHAMPS = [champion["name"] for champion in _champions]

CHAMPS_BY_CLASS = {}
for champion in _champions:
    for league_class in champion["classes"]:
        CHAMPS_BY_CLASS.setdefault(league_class, []).append(champion["name"])

CHAMPS_BY_GENDER = {}
for champion in _champions:
    CHAMPS_BY_GENDER.setdefault(champion["gender"], []).append(champion["name"])

CHAMPS_BY_LGBT = {}
for champion in _champions:
    CHAMPS_BY_LGBT.setdefault(champion["lgbt"], []).append(champion["name"])

CHAMPS_BY_COMPLEXION = {}
for champion in _champions:
    complexion = str(champion["complexion"])
    CHAMPS_BY_COMPLEXION.setdefault(complexion, []).append(champion["name"])


CHAMP_IMAGES_FILENAMES = glob.glob(os.path.join(RESOURCE_DIR, "images/*.png"))
IMAGE_BY_CHAMP_ID = {}
for champ_image_filename in CHAMP_IMAGES_FILENAMES:
    IMAGE_BY_CHAMP_ID[os.path.basename(champ_image_filename).replace(".png", "")] = Image.open(champ_image_filename)
