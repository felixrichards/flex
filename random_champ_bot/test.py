import sys
from champs import random_champ_weighted

if __name__ == "__main__":
    N = 40
    filter_strs = None
    if len(sys.argv) > 1:
        N = int(sys.argv[1])
    if len(sys.argv) > 2:
        filter_strs = sys.argv[2:]

    if filter_strs:
        champs = random_champ_weighted.get_random_champs_with_filters(N=N, filter_strs=filter_strs)
        img = random_champ_weighted.make_grid_from_champs(champs, force_line=True)
    else:
        selected_champs_by_role = random_champ_weighted.get_random_champs_by_role_weighted(N=N)
        champs = sum(selected_champs_by_role.values(), start=[])
        img = random_champ_weighted.make_grid_from_champs_by_role(selected_champs_by_role)
    img.save("test.png")
    print(", ".join(champs))
