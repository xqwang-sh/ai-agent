# Prerequisite handout

- Write for teachers who have only used Office and have no programming background. Explain necessary terms before using them.
- Separate concepts from optional practical work. Explain model access, cloud versus local deployment, Harness and the tool loop, data APIs, and document formats before asking learners to operate a computer.
- Explain SiliconFlow in model access, alongside model size and local compute requirements. Do not place a standalone provider-introduction section under Harness/Agent.
- Organize the data-source table by data type, mixing relevant domestic and international options. Distinguish hosted HTTP services from local libraries, free access from account/Key/points requirements, and company records from survey microdata.
- Begin practice with an existing-tool selector. Selecting any existing Agent/Harness hides the entire OpenCode/DeepSeek installation detail. Without an existing selection, show the collapsed recommended route. All shared prompts address the learner's own Agent.
- Place the installation detail immediately after that selector, before the workspace section. New users install OpenCode and obtain/configure the DeepSeek Key first, then create a workspace, open it as a project and select the model. Keep route messages and the entry table in that order.
- Do not add completion checkboxes, a readiness counter, a final self-check, or a completion report. Each optional action explains its purpose and visible result; application acceptance belongs to the individual lectures.
- Test Node.js/Python with a minimal calculation. Do not generate a webpage solely for environment checking.
- Do not add a practice archive, starter application, fixture attachment or prepared sample-document download. All instructions and checks belong in handout.md. Learners create their own small text and use existing non-sensitive documents.
- Cover Word, PPT and PDF. Explain usable text layers, OCR and visual reading without claiming one extension guarantees readability.
- Each action needs a result the learner can personally inspect and a concrete recovery path. Keep registration, configuration, successful API calls and correct business output distinct.
- handout.md is the sole prose source. build.py generates the standalone HTML using lesson two's base design. Browser scripts may handle only reading conveniences, never credentials or service requests.
- Keep typography aligned with lessons two and three: inherit base body, table, prompt and copy-control sizes. Map nested topic headings to the lecture step-title scale and smaller headings to the lecture subheading scale, including mobile layouts. Do not add a separate enlarged reading scale.
- Rebuild and export via build.py after edits. Do not edit generated index.html or the course module's exported copies independently.
