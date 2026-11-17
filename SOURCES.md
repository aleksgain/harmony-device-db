# Sources and credits

## Harmony IR archive

All device data in this repository and its releases comes from
**[pickysysadmin/logitech-harmony-ir-archive](https://github.com/pickysysadmin/logitech-harmony-ir-archive)**.
The exact upstream tag, commit and tree hash are pinned in
[`archive.lock.json`](archive.lock.json).

That archive covers about 278,000 devices from 7,900 manufacturers, 13.3 million
commands, and 684 Logitech IR protocol definitions, with ready-to-send Pronto Hex
for nearly every infrared command. Thank you to its author, and to the projects
credited in its README (Remote Central, harmony-hub-root, and others), for
preserving this data after Logitech's services were wound down.

## Licence of the data

The upstream author dedicates **their contributions** (the Pronto conversions,
the schema and the organisation of the data) under
[CC0 1.0 Universal](api/v1/LICENSE-DATA).

The upstream README also states that the **underlying IR codes and protocol
definitions originate with Logitech**, and that their copyright status is not
established. CC0 waives the archive author's rights, not anyone else's. Harmony
Revival redistributes the data on the same basis and makes no further claim. If
you build something commercial on it, evaluate that yourself.

## Licence of this repository

The scripts, workflows and documentation in this repository are licensed under the
[Apache License 2.0](LICENSE). That licence does not extend to the data.
