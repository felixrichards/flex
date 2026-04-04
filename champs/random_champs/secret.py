import os

from PIL import Image

from .. import myresources
from .random_champ_weighted import IMAGE_SIZE


CHAMP_STR_TO_CHAMP = {
    "BARD": "Bard",
    "MILIO": "Milio",
    "ZAC": "Zac",
    "MISS FORTUNE": "Miss Fortune",
    "MF": "Miss Fortune",
    "KAYLE": "Kayle",
    "ELISE": "Elise",
    "QIYANA": "Qiyana",
    "VOLI": "Volibear",
    "VOLIBEAR": "Volibear",
    "LILLIA": "Lillia",
    "KAISA": "Kai'Sa",
    "KAI'SA": "Kai'Sa",
    "VAYNE": "Vayne",
    "SHEN": "Shen",
}
OTP_CHAMPS = list(CHAMP_STR_TO_CHAMP.keys())

CHAMP_TO_OTP_IMAGE_PATH = {
    "Bard": "brandon1.png",
    "Milio": "sean1.png",
    "Zac": "felix1.png",
    "Miss Fortune": "laurel1.png",
    "Kayle": "andreas1.png",
    "Elise": "minz1.png",
    "Qiyana": "rich1.png",
    "Volibear": "jake1.png",
    "Lillia": "jay1.png",
    "Kai'Sa": "wyn1.png",
    "Vayne": "sam1.png",
    "Shen": "dylan1.png",
}


def get_champ_and_img(champ_str):
    champ = CHAMP_STR_TO_CHAMP[champ_str.upper()]
    imgpath = CHAMP_TO_OTP_IMAGE_PATH[champ]
    img = Image.open(os.path.join(myresources.RESOURCE_DIR, f"images/secret/{imgpath}")).resize((IMAGE_SIZE, IMAGE_SIZE))
    return champ, img
