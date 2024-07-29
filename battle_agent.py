from openai import OpenAI
from typing import Dict, Any, Union
from environment import PokemonShowdownEnv, GameState, Pokemon, PokemonMove, Player
import os
from dotenv import load_dotenv
import re
import time

# TODO: RAG For Type Matchups (Optimization)
# TODO: Disillation from larger model to smaller model (Optimization)
# TODO: Implement different prompting techniques (Optimization)
# TODO: Add Item and Ability Descriptions (Optimization)
# TODO: Fix Battle Log (Optimization) **Done**
# TODO: Add a way to switch pokemon when dead. (Bug)
# TODO: Error when enemy pokemon dies. (Bug)
# TODO: Error when we die. (Bug)
# TODO: Clean code (functions and classes)


class Agent:
    def __init__(self, client: OpenAI, env: GameState, system: str = "") -> None:
        self.client = client
        self.system = system
        self.env = env
        self.messages: list = []
        if self.system:
            self.messages.append({"role": "system", "content": system})

    def __call__(self, observation: Union[Dict[str, Any], str], print_message: bool = False) -> str:
        if isinstance(observation, dict):
            message = self.format_observation(observation, self.env)
        else:
            message = observation
        self.messages.append({"role": "user", "content": message})
        print(f"{message}")
        
        # Write message to a text file
        with open("pokemonshowdown/conversation_log.txt", "a", encoding="utf-8") as f:
            f.write(f"User: {message}\n")
        
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        print(f"{result}")
        
        # Write result to the same text file
        with open("pokemonshowdown/conversation_log.txt", "a", encoding="utf-8") as f:
            f.write(f"Assistant: {result}\n\n")
        
        #return self.parse_action(result)
        return result

    def execute(self):
        completion = self.client.chat.completions.create(
            messages=self.messages,
            model="meta-llama/llama-3.1-405b-instruct",
            extra_body={
                "temperature": 0.0,
                #"max_tokens": 100,
                "provider": {"order": ["Fireworks", "OctoAI"], 
                },
            },
        )
        return completion.choices[0].message.content
    
    def battle_loop(self, max_iterations=100):
        observation = self.env.reset()
        done = False
        i = 0

        while not done and i < max_iterations:
            i += 1
            
            result = self(observation)
            #print(result)

            if "PAUSE" in result:
                action = re.findall(r"Action: (select_move|switch_pokemon): (.+)", result, re.IGNORECASE)
                if action:
                    action_type, action_name = action[0]
                    action_dict = {
                        "type": "move" if action_type == "select_move" else "switch",
                        f"{'move' if action_type == 'select_move' else 'switch'}_name": action_name
                    }
                    if action_type == "select_move" and action_name == "Terastallize":
                        observation = self.env.step(action_dict)
                        #next_prompt = f"Observation: {observation}"
                        #self.messages.append({"role": "user", "content": next_prompt})
                        #print(next_prompt)
                        continue
                    observation, _, _, _ = self.env.step(action_dict)
                    #next_prompt = f"Observation: Action taken. New game state:\n{self.format_observation(observation, self.env)}"
                    #self.messages.append({"role": "user", "content": next_prompt})
                    #print(next_prompt)
                else:
                    print("Observation: Invalid action")
                continue

            if "Answer:" in result:
                end_result = self.parse_action(result)
                #observation, reward, done, info = self.env.step(end_result)
                observation, _, _, _ = self.env.step(end_result)
                print(f"End Results: {end_result}")
                break

        self.env.close()
        #return reward
    
    

    def format_observation(self, observation: Dict[str, Any], env: GameState) -> str:
        active_pokemon = observation['p1 Active Pokemon']
        opponent_pokemon = observation['p2 Active Pokemon']
        
        message = f"""Current game state:
                    Turn: {observation['turn']}
                    
                    Recent battle events:
                    {observation['chat_log']}
                    
                    Terastallize Available: {"Yes" if self.env.game_state.player.can_terastallize else "No"}

                    Your active Pokémon: {active_pokemon.name} (Level {active_pokemon.level})
                    Current Types: {', '.join(active_pokemon.current_types)}
                    Base Types: {', '.join(active_pokemon.base_types)}
                    Terastallized: {"Yes" if active_pokemon.terastallized else "No"}
                    Tera Type: {active_pokemon.tera_type}
                    HP: {active_pokemon.current_hp}/{active_pokemon.max_hp} ({active_pokemon.hp_percentage}%)
                    Ability: {active_pokemon.ability}
                    Item: {active_pokemon.item}
                    Stats: {self.format_stats(active_pokemon.current_stats)}

                    Available moves:
                    {self.format_moves(active_pokemon.moves)}

                    Opponent's active Pokémon: {opponent_pokemon.name} (Level {opponent_pokemon.level})
                    Current Types: {', '.join(opponent_pokemon.current_types)}
                    Base Types: {', '.join(opponent_pokemon.base_types)}
                    Terastallized: {"Yes" if opponent_pokemon.terastallized else "No"}
                    Tera Type: {opponent_pokemon.tera_type}
                    HP: {opponent_pokemon.hp_percentage}%
                    Possible abilities: {', '.join(opponent_pokemon.possible_abilities)}
                    Opponent Speed Range: {opponent_pokemon.opponent_speed_range}

                    Your team:
                    {self.format_team(observation['p1 Team Revealed'])}

                    Opponent's revealed Pokémon:
                    {self.format_team(observation['p2 Team Revealed'])}

                    What action do you want to take? Analyze the situation, considering factors including, but not limited to:
                        1. Recent battle events and their impact on the current state
                        2. Type matchups for both active Pokémon and potential switches
                        3. Abilities of active Pokémon and known abilities of team members
                        4. Available moves for the active Pokémon and known moves of team members
                        5. Potential Terastallization strategies for the active Pokémon and team members
                        6. Items held by the active Pokémon and team members
                        7. Current HP and status conditions of all Pokémon
                        8. Potential threats from the opponent's revealed Pokémon

                    Based on this analysis, decide whether to use a move with the active Pokémon or switch to another Pokémon that may have an advantage in the current situation. Consider both offensive and defensive strategies, as well as any other relevant factors not explicitly listed above. Be sure to take into account the recent battle events and how they affect your decision.
                """

        return message

    def format_moves(self, moves):
        formatted_moves = []
        for i, move in enumerate(moves):
            move_info = f"{i+1}. {move.name} (Type: {move.type}, Category: {move.category}, "
            move_info += f"Power: {move.power if move.power else 'N/A'}, "
            move_info += f"Accuracy: {move.accuracy if move.accuracy else 'N/A'}, "
            move_info += f"PP: {move.current_pp}/{move.max_pp})"
            if move.description:
                move_info += f"\n   Description: {move.description}"
            formatted_moves.append(move_info)
        return "\n".join(formatted_moves)

    def format_team(self, team):
        formatted_team = []
        for pokemon in team:
            pokemon_info = f"- {pokemon.name} (Level {pokemon.level})"
            pokemon_info += f"\n  Current Types: {', '.join(pokemon.current_types)}"
            pokemon_info += f"\n  Base Types: {', '.join(pokemon.base_types)}"
            pokemon_info += f"\n  Terastallized: {'Yes' if pokemon.terastallized else 'No'}"
            if pokemon.tera_type != 'Unknown':
                pokemon_info += f"\n  Tera Type: {pokemon.tera_type}"
            else:
                pokemon_info += f"\n  Tera Type: Not known"
            pokemon_info += f"\n  HP: {pokemon.hp_percentage}%"
            if pokemon.ability:
                pokemon_info += f"\n  Ability: {pokemon.ability}"
            else:
                pokemon_info += f"\n  Ability: Not known"
            if pokemon.item:
                pokemon_info += f"\n  Item: {pokemon.item}"
            else:
                pokemon_info += f"\n  Item: Not known"
                
            # Add moves information
            pokemon_info += "\n  Moves:"
            if pokemon.moves:
                for i, move in enumerate(pokemon.moves, 1):
                    move_info = f"\n    {i}. {move.name}"
                    if move.type:
                        move_info += f" (Type: {move.type}"
                        if move.category:
                            move_info += f", Category: {move.category}"
                        move_info += ")"
                    if move.power is not None:
                        move_info += f"\n       Power: {move.power}"
                    if move.accuracy:
                        move_info += f", Accuracy: {move.accuracy}"
                    if move.current_pp is not None and move.max_pp is not None:
                        move_info += f", PP: {move.current_pp}/{move.max_pp}"
                    else: 
                        move_info += f", PP: Not known"
                    if move.description:
                        move_info += f"\n       Description: {move.description}"
                    pokemon_info += move_info
            else:
                pokemon_info += "\n    Moves not known"
                
            formatted_team.append(pokemon_info)
        return "\n".join(formatted_team)

    def format_stats(self, stats):
        if not stats:
            return "Unknown"
        return ", ".join([f"{stat}: {value}" for stat, value in stats.items()])

    def parse_action(self, message: str) -> Dict[str, Any]:
        lines = message.strip().split('\n')
        action_line = None
        for line in lines:
            if line.lower().startswith("action:"):
                action_line = line.lower()
                break
        
        if action_line is None:
            raise ValueError(f"No action found in the message:\n{message}")

        if "move:" in action_line:
            move_name = action_line.split('move:')[1].strip()
            return {"type": "move", "move_name": move_name}
        elif "switch:" in action_line:
            pokemon_name = action_line.split('switch:')[1].strip()
            return {"type": "switch", "switch_name": pokemon_name}
        else:
            raise ValueError(f"Invalid action format: {action_line}")
        
def main():
    load_dotenv()
    
    env = PokemonShowdownEnv(username="Poke214915", password="LLMAgent1234")
    client = OpenAI(api_key=os.getenv("OPENROUTER_API_KEY"), 
                    base_url="https://openrouter.ai/api/v1",)
    
    system_prompt = """
    You are an AI agent playing Pokémon Showdown. Your task is to make strategic decisions in battles.
    You run in a loop of Thought, Action, PAUSE, Observation.
    At the end of the loop, you output an Answer, which should be your final action decision.

    Use Thought to describe your reasoning about the current battle situation.
    Use Action to choose one of the available actions - then return PAUSE.
    Observation will be the result of taking those actions.

    Your available actions are:

    select_move:
    e.g. select_move: Surf
    Selects the move from the list of available moves.

    switch_pokemon:
    e.g. switch_pokemon: Alakazam
    Switches to a non-fainted Pokémon from your team.

    Example session:

    Observation: Current game state:
    Turn: 1
    
    Recent Battle Events:
    Battle started between poke2149152143124 and Poke214915!
    poke2149152143124 sent out Pikachu!
    Go! Enamorus!
    
    Terastallize Available: Yes

    Your active Pokémon: Enamorus (Level 83)
    Current Types: Fairy, Flying
    Base Types: Fairy, Flying
    Tera Available: Yes
    Terastallized: No
    Tera Type: Ground
    HP: 259/259 (100.0%)
    Ability: Overcoat
    Item: Weakness Policy
    Stats: Atk: 195, Def: 230, SpA: 272, SpD: 214, Spe: 124

    Available moves:
    1. Agility (Type: Psychic, Category: Status, Power: N/A, Accuracy: can't miss, PP: 48/48)
       Description: Raises the user's Speed by 2 stages.
    2. Moonblast (Type: Fairy, Category: Special, Power: N/A, Accuracy: 100%, PP: 24/24)
       Description: Has a 30% chance to lower the target's Special Attack by 1 stage.
    3. Earth Power (Type: Ground, Category: Special, Power: N/A, Accuracy: 100%, PP: 16/16)
       Description: Has a 10% chance to lower the target's Special Defense by 1 stage.
    4. Mystical Fire (Type: Fire, Category: Special, Power: N/A, Accuracy: 100%, PP: 16/16)
       Description: Has a 100% chance to lower the target's Special Attack by 1 stage.
    5. Terastallize (Type: Ground, Category: Status, Power: N/A, Accuracy: N/A, PP: None/None)
       Description: Terastallize into Ground type

    Opponent's active Pokémon: Pikachu (Level 93)
    Current Types: Electric
    Base Types: Electric
    Terastallized: No
    Tera Type: Unknown
    HP: 100%
    Possible abilities: Static, Lightning Rod
    Opponent Speed Range: (172, 220)

    Your team:
    1. Enamorus (Level 83)
      Current Types: Fairy, Flying
      Base Types: Fairy, Flying
      Terastallized: No
      Tera Type: Ground
      HP: 100.0%
      Ability: Overcoat
      Item: Weakness Policy
      Moves:
        1. Agility (Type: Psychic, Category: Status), Accuracy: can't miss, PP: 48/48
           Description: Raises the user's Speed by 2 stages.
        2. Moonblast (Type: Fairy, Category: Special), Accuracy: 100%, PP: 24/24
           Description: Has a 30% chance to lower the target's Special Attack by 1 stage.
        3. Earth Power (Type: Ground, Category: Special), Accuracy: 100%, PP: 16/16
           Description: Has a 10% chance to lower the target's Special Defense by 1 stage.
        4. Mystical Fire (Type: Fire, Category: Special), Accuracy: 100%, PP: 16/16
           Description: Has a 100% chance to lower the target's Special Attack by 1 stage.
        5. Terastallize (Type: Ground, Category: Status), PP: Not known
           Description: Terastallize into Ground type
    2. Gogoat (Level 88)
      Current Types: Grass
      Base Types: Grass
      Terastallized: No
      Tera Type: Water
      HP: 100.0%
      Ability: Sap Sipper
      Item: Leftovers
      Moves:
        1. Horn Leech (Type: Grass, Category: physical)
           Power: 75, Accuracy: 100, PP: Not known
           Description: User recovers half the HP inflicted on opponent.
        2. Bulk Up (Type: Fighting, Category: status), PP: Not known
           Description: Raises user's Attack and Defense.
        3. Milk Drink (Type: Normal, Category: status), PP: Not known
           Description: User recovers half its max HP.
        4. Earthquake (Type: Ground, Category: physical)
           Power: 100, Accuracy: 100, PP: Not known
           Description: Power is doubled if opponent is underground from using Dig.
    3. Leafeon (Level 88)
      Current Types: Grass
      Base Types: Grass
      Terastallized: No
      Tera Type: Dark
      HP: 100.0%
      Ability: Chlorophyll
      Item: Leftovers
      Moves:
        1. Substitute (Type: Normal, Category: status), PP: Not known
           Description: Uses HP to creates a decoy that takes hits.
        2. Leaf Blade (Type: Grass, Category: physical)
           Power: 90, Accuracy: 100, PP: Not known
           Description: High critical hit ratio.
        3. Swords Dance (Type: Normal, Category: status), PP: Not known
           Description: Sharply raises user's Attack.
        4. Knock Off (Type: Dark, Category: physical)
           Power: 65, Accuracy: 100, PP: Not known
           Description: Removes opponent's held item for the rest of the battle.
    4. Lunala (Level 70)
      Current Types: Psychic, Ghost
      Base Types: Psychic, Ghost
      Terastallized: No
      Tera Type: Fairy
      HP: 100.0%
      Ability: Shadow Shield
      Item: Leftovers
      Moves:
        1. Psyshock (Type: Psychic, Category: special)
           Power: 80, Accuracy: 100, PP: Not known
           Description: Inflicts damage based on the target's Defense, not Special Defense.
        2. Moonlight (Type: Fairy, Category: status), PP: Not known
           Description: User recovers HP. Amount varies with the weather.
        3. Calm Mind (Type: Psychic, Category: status), PP: Not known
           Description: Raises user's Special Attack and Special Defense.
        4. Moongeist Beam (Type: Ghost, Category: special)
           Power: 100, Accuracy: 100, PP: Not known
           Description: Ignores the target's ability.
    5. Terrakion (Level 79)
      Current Types: Rock, Fighting
      Base Types: Rock, Fighting
      Terastallized: No
      Tera Type: Fighting
      HP: 100.0%
      Ability: Justified
      Item: Life Orb
      Moves:
        1. Close Combat (Type: Fighting, Category: physical)
           Power: 120, Accuracy: 100, PP: Not known
           Description: Lowers user's Defense and Special Defense.
        2. Stone Edge (Type: Rock, Category: physical)
           Power: 100, Accuracy: 80, PP: Not known
           Description: High critical hit ratio.
        3. Swords Dance (Type: Normal, Category: status), PP: Not known
           Description: Sharply raises user's Attack.
        4. Earthquake (Type: Ground, Category: physical)
           Power: 100, Accuracy: 100, PP: Not known
           Description: Power is doubled if opponent is underground from using Dig.
    6. Pachirisu (Level 96)
      Current Types: Electric
      Base Types: Electric
      Terastallized: No
      Tera Type: Flying
      HP: 100.0%
      Ability: Volt Absorb
      Item: Assault Vest
      Moves:
        1. Super Fang (Type: Normal, Category: physical), Accuracy: 90, PP: Not known
           Description: Always takes off half of the opponent's HP.
        2. U-turn (Type: Bug, Category: physical)
           Power: 70, Accuracy: 100, PP: Not known
           Description: User switches out immediately after attacking.
        3. Thunderbolt (Type: Electric, Category: special)
           Power: 90, Accuracy: 100, PP: Not known
           Description: May paralyze opponent.
        4. Nuzzle (Type: Electric, Category: physical)
           Power: 20, Accuracy: 100, PP: Not known
           Description: Paralyzes opponent.

    Opponent's revealed Pokémon:
    - Pikachu (Level 93)
      Current Types: Electric
      Base Types: Electric
      Terastallized: No
      Tera Type: Not known
      HP: 100%
      Ability: Not known
      Item: Not known
      Moves:
        Moves not known

    What action do you want to take? Analyze the situation, considering factors including, but not limited to:
    1. Recent battle events and their impact on the current state
    2. Type matchups for both active Pokémon and potential switches
    3. Abilities of active Pokémon and known abilities of team members
    4. Available moves for the active Pokémon and known moves of team members
    5. Potential Terastallization strategies for the active Pokémon and team members
    6. Items held by the active Pokémon and team members
    7. Current HP and status conditions of all Pokémon
    8. Potential threats from the opponent's revealed Pokémon

    Based on this analysis, decide whether to use a move with the active Pokémon or switch to another Pokémon that may have an advantage in the current situation. Consider both offensive and defensive strategies, as well as any other relevant factors not explicitly listed above. Be sure to take into account the recent battle events and how they affect your decision.

    Thought: Let's analyze the current situation based on the factors provided:

    1. Type matchups:
       - Enamorus (Fairy/Flying) vs Pikachu (Electric)
       - Fairy is neutral against Electric, but Flying is weak to Electric
       - Overall, we're at a slight disadvantage in terms of type matchup

    2. Abilities:
       - Enamorus has Overcoat, which protects against weather damage but isn't particularly useful in this matchup
       - Pikachu's ability is unknown, but common abilities like Static or Lightning Rod could be problematic

    3. Available moves:
       - Moonblast: Neutral damage with chance to lower Sp. Atk
       - Earth Power: Could be super effective if we Terastallize to Ground
       - Agility: Could help us outspeed Pikachu in future turns
       - Mystical Fire: Not very effective against Electric types

    4. Terastallization strategy:
       - Enamorus can Terastallize into Ground type, which would make us immune to Electric moves and allow for super effective Earth Power

    5. Items:
       - Enamorus is holding a Weakness Policy, which could boost our stats if hit by a super effective Electric move

    6. Current HP and status:
       - Both Pokémon are at full HP with no status conditions

    7. Potential threats:
       - Pikachu likely has strong Electric-type moves that could be super effective against our Flying type

    Considering these factors, we have two strong options:
    1. Terastallize into Ground type and use Earth Power for a super effective hit and Electric immunity
    2. Use Moonblast for a safe, neutral damage option with a chance to lower Sp. Atk

    The more aggressive and potentially rewarding strategy is to Terastallize and use Earth Power. This will provide immediate type advantage and potentially knock out Pikachu quickly.

    Action: select_move: Terastallize
    PAUSE

    Observation: You have selected to terastallize Enamorus into the Ground type.

    Thought: Now that we've terastallized into Ground type, we're immune to Electric moves and can use Earth Power for super effective damage. This is the perfect time to strike.

    Action: select_move: Earth Power
    PAUSE

    Observation: Current game state:
    Turn: 2

    Recent Battle Events:
    Enamorus has Terastallized into the Ground-type
    Pikachu used Volt Tackle!
    It doesn't affect the opposing Enamorus...
    The opposing Enamorus used Earth Power!
    It's super effective!
    (Pikachu lost 100% of its health!)
    Pikachu fainted!
    Go! Meowscarada!

    
    Terastallize Available: Yes
    
    Your active Pokémon: Enamorus (Level 83)
    ...

    Thought: Our strategy was even more effective than anticipated. We successfully Terastallized into Ground-type, making us immune to Pikachu's Volt Tackle. Our Earth Power was super effective and knocked out Pikachu in one hit. Now, the opponent has sent out Meowscarada, which is a Grass/Dark type. We need to reassess our strategy for this new threat.

    Action: select_move: Earth Power
    PAUSE

    You will be called again with a new Observation. Continue this process until you have made a final decision.

    If you observe the game ending based on the recent battle events section, output "Answer: Winner" if you won or "Answer: Loser" if you lost. This will conclude the battle.

    Answer: Winner

    Now it's your turn to analyze the battle situation and make strategic decisions. Remember, Terastallization is a new mechanic that changes the current type of the Pokémon into whatever the Tera type is, but can only be used by one pokemon per team. This can be used to gain type advantages or remove weaknesses during battle. When you choose to Terastallize, you must also select a move to use in the same turn.
    """.strip()
    
    agent = Agent(client= client, env= env, system= system_prompt)
    
    final_reward = agent.battle_loop()
    #print(f"Battle finished with reward: {final_reward}")

if __name__ == "__main__":
    main()