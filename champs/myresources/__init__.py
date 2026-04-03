import glob
import os
import json
from PIL import Image

RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))


CHAMPS_PLAYERS_MANIFEST_FILENAME = "champs_players_manifest.json"
with open(os.path.join(RESOURCE_DIR, CHAMPS_PLAYERS_MANIFEST_FILENAME), "r") as f:
    CHAMPS_PLAYERS_MANIFEST = json.load(f)


CHAMPS_WITH_ROLE_DATA_FILENAME = "champs_with_roles.txt"
with open(os.path.join(RESOURCE_DIR, CHAMPS_WITH_ROLE_DATA_FILENAME), "r") as f:
    CHAMPS_WITH_ROLE_DATA = f.read().split("\n")


ROLES_BY_CHAMP_FILENAME = "roles_by_champ.txt"
with open(os.path.join(RESOURCE_DIR, ROLES_BY_CHAMP_FILENAME), "r") as f:
    ROLES_BY_CHAMP = {}
    for data in f.read().split('\n'):
        champ, role = data.split("\t")[0], data.split("\t")[1].split(",")
        ROLES_BY_CHAMP[champ] = role

CHAMPS_BY_ROLE_FILENAME = "champs_by_role.txt"
with open(os.path.join(RESOURCE_DIR, CHAMPS_BY_ROLE_FILENAME), "r") as f:
    CHAMPS_BY_ROLE = {}
    for data in f.read().split('\n'):
        role, champs = data.split("\t")[0], data.split("\t")[1].split(",")
        CHAMPS_BY_ROLE[role] = champs

CHAMPS_BY_DAMAGE_TYPE_FILENAME = "champs_by_damage_type.txt"
with open(os.path.join(RESOURCE_DIR, CHAMPS_BY_DAMAGE_TYPE_FILENAME), "r") as f:
    CHAMPS_BY_DAMAGE_TYPE = {}
    for data in f.read().split('\n'):
        damage_type, champs = data.split("\t")[0], data.split("\t")[1].split(",")
        CHAMPS_BY_DAMAGE_TYPE[damage_type] = champs

CHAMPS_FILENAME = "champs.txt"
with open(os.path.join(RESOURCE_DIR, CHAMPS_FILENAME), "r") as f:
    CHAMPS = f.read().split('\n')


CLASSES_WITH_CHAMP_DATA_FILENAME = "champs_by_class.txt"
with open(os.path.join(RESOURCE_DIR, CLASSES_WITH_CHAMP_DATA_FILENAME), "r") as f:
    CHAMPS_BY_CLASS = {}
    for data in f.read().split('\n'):
        league_class, champs = data.split("\t")[0], data.split("\t")[1].split(",")
        CHAMPS_BY_CLASS[league_class] = champs


CHAMPS_BY_GENDER_FILENAME = "champs_by_gender.txt"
with open(os.path.join(RESOURCE_DIR, CHAMPS_BY_GENDER_FILENAME), "r") as f:
    CHAMPS_BY_GENDER = {}
    for data in f.read().split('\n'):
        gender_type, champs = data.split("\t")[0], data.split("\t")[1].split(",")
        CHAMPS_BY_GENDER[gender_type] = champs


CHAMPS_BY_LGBT_FILENAME = "champs_by_lgbt.txt"
with open(os.path.join(RESOURCE_DIR, CHAMPS_BY_LGBT_FILENAME), "r") as f:
    CHAMPS_BY_LGBT = {}
    for data in f.read().split('\n'):
        lgbt_type, champs = data.split("\t")[0], data.split("\t")[1].split(",")
        CHAMPS_BY_LGBT[lgbt_type] = champs


CHAMPS_BY_COMPLEXION_FILENAME = "champs_by_complexion.txt"
with open(os.path.join(RESOURCE_DIR, CHAMPS_BY_COMPLEXION_FILENAME), "r") as f:
    CHAMPS_BY_COMPLEXION = {}
    for data in f.read().split('\n'):
        complexion, champs = data.split("\t")[0], data.split("\t")[1].split(",")
        CHAMPS_BY_COMPLEXION[complexion] = champs



CHAMP_IMAGES_FILENAMES = glob.glob(os.path.join(RESOURCE_DIR, "images/*.png"))
IMAGE_BY_CHAMP_ID = {}
for champ_image_filename in CHAMP_IMAGES_FILENAMES:
    IMAGE_BY_CHAMP_ID[os.path.basename(champ_image_filename).replace(".png", "")] = Image.open(champ_image_filename)
