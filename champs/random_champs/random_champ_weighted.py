import math
import random

from PIL import Image

from . import filters
from . import constants
from .. import myresources


IMAGE_SIZE = 60


def _champ_to_champ_id(champ):
    if champ == "Wukong":
        return "MonkeyKing"
    if champ == "Nunu & Willump":
        return "Nunu"
    if champ == "Renata Glasc":
        return "Renata"
    if champ == "Kog'Maw":
        return "KogMaw"
    if champ == "LeBlanc":
        return "Leblanc"
    if champ == "K'Sante":
        return "KSante"
    if champ == "Rek'Sai":
        return "RekSai"
    if "'" in champ:
        champ = champ[:champ.find("'")] + champ[champ.find("'"):].lower()
    return champ.replace(" ", "").replace(".", "").replace("'", "")


def get_random_champs_by_role_weighted(N, fearless_bans=[]):
    ceiled_N = math.ceil(N / 5) * 5
    champs_by_role = {role: [] for role in constants.ROLES}
    champs_by_occurence = {}
    inverse_champs_by_occurence = {}

    for champ_data in myresources.CHAMPS_WITH_ROLE_DATA:
        champ, parsed_roles = champ_data.split("\t")[0], champ_data.split("\t")[1:-1]
        champs_by_occurence[champ] = 0
        for parsed_role, ROLE in zip(parsed_roles, constants.ROLES):
            if parsed_role:
                champs_by_role[ROLE].append(champ)
                champs_by_occurence[champ] += 1
        inverse_champs_by_occurence[champ] = round(1 / champs_by_occurence[champ] * 60)


    selected_champs_by_role = {role: [] for role in constants.ROLES}
    all_picked_champs = []
    for role in constants.ROLES:
        weighted_champs = sum([[champ] * inverse_champs_by_occurence[champ] for champ in champs_by_role[role]], start=[])
        random.shuffle(weighted_champs)
        i = 0
        while i < ceiled_N // 5:
            potential_champ = weighted_champs.pop()
            if (
                potential_champ not in all_picked_champs
                and potential_champ not in selected_champs_by_role[role]
                and potential_champ not in fearless_bans
            ):
                all_picked_champs.append(potential_champ)
                selected_champs_by_role[role].append(potential_champ)
                i += 1

    if N < ceiled_N:
        roles_to_remove_one = []
        shuffled_roles = list(constants.ROLES)
        random.shuffle(shuffled_roles)
        for _ in range(ceiled_N - N):
            roles_to_remove_one.append(shuffled_roles.pop())
        for role in roles_to_remove_one:
            if selected_champs_by_role[role]:
                selected_champs_by_role[role].pop()

    return selected_champs_by_role


def get_random_champs_with_filters(N, filter_strs):
    filter_objects = filters.parse_filters(filter_strs)
    filtered_champs = myresources.CHAMPS.copy()
    for filter_object in filter_objects:
        filtered_champs = filter_object.filter(filtered_champs)
    
    random.shuffle(filtered_champs)

    return filtered_champs[:N]


def make_grid_from_champs_by_role(champs_by_role):
    if any(len(champs) == 0 for champs in champs_by_role.values()):
        champs = sum(champs_by_role.values(), start=[])
        return make_grid_from_champs(champs)
    max_champs_per_role = max(len(champs) for champs in champs_by_role.values())
    width = max_champs_per_role
    height = 5

    grid = Image.new('RGB', (width * IMAGE_SIZE, height * IMAGE_SIZE))
    for row, role in enumerate(constants.ROLES):
        row_grid = make_grid_from_champs(champs=champs_by_role[role], height=1, width=width)
        grid.paste(row_grid, (0 * IMAGE_SIZE, row * IMAGE_SIZE))
    return grid


def make_grid_from_champs(champs, width=None, height=None, force_square=False, force_line=False):
    champ_images = [myresources.IMAGE_BY_CHAMP_ID[_champ_to_champ_id(champ)] for champ in champs]
    champ_images = [champ_image.resize((IMAGE_SIZE, IMAGE_SIZE)) for champ_image in champ_images]
    
    if not (width and height):
        if len(champs) % 5 == 0:
            width = len(champs) // 5
            height = 5
        else:
            force_square = True
        if force_square:
            width = math.ceil(math.sqrt(len(champs)))
            height = round(math.sqrt(len(champs)))
        if force_line:
            width = min(10, len(champs))
            height = math.ceil(len(champs) / width)

    grid = Image.new('RGB', (width * IMAGE_SIZE, height * IMAGE_SIZE))
    for index, img in enumerate(champ_images):
        row = index // width
        col = index % width
        grid.paste(img, (col * IMAGE_SIZE, row * IMAGE_SIZE))
    return grid
