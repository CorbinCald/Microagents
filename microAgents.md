# Microagent architecture

## Subagents but more focused, more parallelized, and much faster.

### Planning

- Orchestration LLM will separate a complex tasks into detailed microtasks, scoped to one simple change at a time. 
- Orchestration LLM will obtain have full context of any files that need changes (read tool), this can be cached input.

### LLMs:

- Orchestrator: Opus 4.6(+)
- Microagents: Mercury 2 (by Inception)

### Interface Code

- Written by the orchestration LLM.
- Can be parallelized with programmatic tool calling ([https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling))

#### Interface code is token-efficient terminal commands that say:

1. Where to edit (filepath, function, lines)
2. What to change (the low-scope changes to make, string formatted prompt)

#### Examples

microagent deploy --where /home/documents/weather.py:getForecast() --what 'Separate the code that converts celcius to farenheight into its own function' 

microagent deploy --where /bigproject/models:L100-250 --what 'change the temperature of all models to .2'

microagent deploy --where /messyrepo/messyfile --what 'ensure single line spaces between code and double line spaces between functions' 

(note: these commands would usually be serving one prompt/task/project, and such would be orchestrates independently but cohesive of one end-goal)

### Flow

1. Smart orchestration model --[interface code x10]--> Ten mercury 2 microagents
2. Microagents make small-scope, low-risk changes to code.
3. Smart orchestration model sees Diff and either approves changes or orchestrates more microagents

