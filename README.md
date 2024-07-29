# Pokemon-Agents
Building different agents to play through various Pokemon environments. Utilizing different LLM and RL techniques.

## Pokemon Showdown (In Development)
- **Overview**: Utilizing LLMs/RL to battle.
- **Agent Architecture**:
  - LLM-based battling
  - Reinforcement Learning battling (Coming soon)
- **Features**:
  - Team building (Coming Soon)
  - Battle strategies based on current state
    - Move selection and Switch selection
- **Current Progress**:
  - LLM Battling (end to end), further optimization is needed
  - Reasoning improvement
    - Implementing different prompting techniques (CoT, Self-Consistency, ToT, Reflexion, ReAct, PreAct)
    - Type Matchups (RAG)
    - Model Distillation to improve smaller models (Fine Tuning)
  - Environment improvement
    - Finding the most optimal context prompt.

## PokeMMO (In Development)
- **Overview**: Utilizing LLMs/RL for exploration. Hoping to cover the full MMO lifecycle.
- **Agent Capabilities**:
  - Navigation in the game world
  - NPC interactions
  - Battle system integration (Previous implementation will help)
- **Technical Approach** (TBD):
  - Computer vision for game state recognition
  - Action space definition 
  - Learning algorithm details
- **Development Status**:
  - Current brainstorming stage
  - Upcoming features
    - TBD
  - Known issues or limitations
    - TBD

## Future Plans
- Additional environments to be explored
- Performance benchmarks and comparisons

## Note
- Not utilizing Langchain or LlamaIndex to learn without complex abstractions.
