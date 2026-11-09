# Tree325ChangesForFreeCAD
## Dynapath Delta 10 and 20 Post Proccessor
- [x] Write body of script
- [ ] Ammend to fit well with FreeCAD post standards
  - [ ] Make spindle ramp optional
  - [ ] Write a new post that uses the MBPP class hierarchy.
  - [ ] Configure tests.
  - [ ] Submit the machine to the new Machines repo
  - [ ] Turn the script file into a class
  - [ ] 
**from: https://github.com/FreeCAD/FreeCAD/issues/28877**
example machine file: src/Mod/CAM/Machine/machines/<MachineName>.fcm
1. Machine configuration (.fcm file) — physical machine description
    plus output-formatting preferences.
2. Postprocessor class — a Python class inheriting from PostProcessor
    (or an existing subclass like Generic) that implements any
    machine-family-specific G-code behaviour the base class cannot express
    through configuration alone.
3. Unit tests — verify both the machine config and the postprocessor
    output.
- Unit tests
  - What are they?
 
For every migrated postprocessor, write tests covering:
- [ ] Empty path produces valid preamble + postamble
- [ ] File extension is correct
- [ ] Preamble content matches legacy
- [ ] Postamble content matches legacy
- [ ] Unit code (G20/G21 or G70/G71) appears
- [ ] Precision from config is respected
- [ ] Command spacing matches config
- [ ] Line numbering (if enabled) matches format
- [ ] Comments are formatted correctly (symbol, framing)
- [ ] Fixture commands are output correctly (remapped if needed)
- [ ] Tool change sequence is correct (M5 before M6 if required)
- [ ] Coolant commands appear (M7/M8/M9)
- [ ] Drill cycles are handled (translated or native, parameter renaming)
- [ ] Arc commands are correct (absolute vs incremental centres)
- [ ] Modal suppression works
- [ ] Duplicate parameter suppression works
- [ ] Schema defaults populate sparse configs
- [ ] EOF markers or special framing appear
- [ ] Sanity checks fire for known bad configurations
- [ ] export2() pipeline produces valid output
- [ ] Legacy export() pipeline still works (if supported)

