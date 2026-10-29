# iOS original organization acceptance

[Run 40645923724](https://github.com/NoGod3524/EXReader/actions/runs/40645923724), source `3e998ec31cce1fe3d720885f675937dafa358fef`, attempt 1, SDK 3.41: iPhone and iPad simulator jobs both passed the same six native organization cases and retained original test logs and attachments. The fixed-catalog audit authenticates each original archive and its exact steps and screens separately.

The six cases cover shelf create, rename, delete, restore and restart; shelf membership add, restart and removal; tag and series creation and restart; staged operation recovery; a nested shelf and restart; and rejection of a stale edit. The tag and series case does not establish full membership and lifecycle coverage for each kind.

The later SDK 3.42 candidate [40817810353](https://github.com/NoGod3524/EXReader/actions/runs/40817810353) remains failed: iPhone tag lifecycle did not finish original verification, although the iPad six cases passed. No evidence is combined to claim that newer candidate passed. Physical devices, simultaneous sync and final common-source delivery remain open.
