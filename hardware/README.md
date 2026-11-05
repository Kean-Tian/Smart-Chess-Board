# Hardware Reference Files

- `reference/master_pcb.pdf` and `reference/sensor_pcb.pdf`: supplied on 2026-10-26 and retained as original hardware references. They are not the current S2 jumper map. The original PDFs are unchanged.
- `kicad/SCB_Connectors.kicad_pro` and `.kicad_sch`: the connector KiCad project already present in the original SCB directory, retained as project hardware documentation. Its presence does not establish that it is the latest complete master PCB design.

- `reference/SCBSensorPCBV2.kicad_sch`: supplied Sensor PCB V2 schematic used to trace the current decoder, comparator and J1 signal connections. Its J1 order differs from the older sensor reference. The original file was copied without modification.

The retained connector project still contains the original ESP32-S3 design; it has not been relabeled as S2 because the physical Master PCB design is separate from the temporary S2 test harness.

See [PCB_Connection_Map.md](../docs/PCB_Connection_Map.md) for the pin-by-pin firmware GPIO and ribbon-cable mapping.
Personal KiCad session files, automatic backups, and caches are excluded from the main project documentation.
