import re
import time
from typing import List, Dict, Any, Union, Optional, Tuple
from dataclasses import dataclass, field
import logging
import json

from langchain.chat_models import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain.prompts import SystemMessagePromptTemplate
from langchain.agents import Tool, AgentExecutor, LLMSingleActionAgent
from langchain.schema import AgentAction, AgentFinish

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException


from dotenv import load_dotenv
import os

@dataclass
class PokemonMove:
    name: str
    type: Optional[str] = None
    category: Optional[str] = None  # Physical, Special, or Status
    power: Optional[int] = None
    accuracy: Optional[str] = None
    current_pp: Optional[int] = None
    max_pp: Optional[int] = None
    description: Optional[str] = None
    target: Optional[str] = None

@dataclass
class Pokemon:
    name: str
    fainted: bool = False
    level: Optional[int] = None
    current_hp: Optional[int] = None
    max_hp: Optional[int] = None
    hp_percentage: Optional[str] = None
    status_effects: List[str] = field(default_factory=list)
    current_types: List[str] = field(default_factory=list)
    terastallized: bool = False
    tera_type: Optional[str] = None
    base_types: List[str] = field(default_factory=list)
    possible_abilities: List[str] = field(default_factory=list)
    ability: Optional[str] = None
    item: Optional[str] = None
    base_stats: Optional[Dict[str, int]] = None
    current_stats: Optional[Dict[str, int]] = None
    opponent_speed_range: Optional[Tuple[int, int]] = None
    moves: List[PokemonMove] = field(default_factory=list)
    
@dataclass
class Player:
    name: str
    revealed_pokemon: List[Pokemon]
    active_pokemon: Optional[Pokemon]
    can_terastallize: bool = True

@dataclass
class GameState:
    player: Player
    opponent: Player
    turn: int
    chat_log: str
    last_update_failed: bool = False


class PokemonShowdownEnv:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        #self.game_state = self.initialize_game_state()
        #self.setup_driver()
        
    def initialize_game_state(self):
        player = Player(name="p1", revealed_pokemon=[], active_pokemon=None)
        opponent = Player(name="p2", revealed_pokemon=[], active_pokemon=None)
        return GameState(player=player, opponent=opponent, turn=0, chat_log="")

        
    def setup_driver(self):
        # Set up Firefox options
        firefox_options = FirefoxOptions()
        #firefox_options.add_argument("--headless")  # Run in headless mode if you don't need to see the browser
        firefox_options.set_preference("dom.webnotifications.enabled", False)
        firefox_options.set_preference("dom.push.enabled", False)
        self.driver = webdriver.Firefox(options=firefox_options)
        self.driver.get("https://play.pokemonshowdown.com/")
        
    def enter_credentials(self) -> str:
        try:
            # Enter username
            username_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input.textbox.autofocus[name='username']"))
            )
            username_input.clear()
            username_input.send_keys(self.username)
            username_input.send_keys(Keys.RETURN)

            # Enter password if provided
            if self.password:
                password_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input.textbox[name='password'][type='password']"))
                )
                password_input.clear()
                password_input.send_keys(self.password)
                password_input.send_keys(Keys.RETURN)

            return f"Entered credentials for username: {self.username}"
        except Exception as e:
            return f"Error entering credentials: {str(e)}"
        
    def verify_match_found(self, timeout=60) -> bool:
        try:
            # Wait for the battle interface to load
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".battle-log"))
            )
            
            # Check for the "Battle started" message in the log
            battle_log = self.driver.find_element(By.CSS_SELECTOR, ".battle-log")
            if "Battle started" in battle_log.text:
                return True
            
            
            return True
        except Exception as e:
            print(f"Match verification failed: {str(e)}")
            return False
        
    def update_game_state(self):
        try:
            self.game_state.chat_log = self.get_chat_log(self.game_state.turn)
            if self.game_state.turn == 0:
                self.update_revealed_pokemon_from_switch_options()
                for pokemon in self.game_state.player.revealed_pokemon:
                    for move in pokemon.moves:
                        self.update_move_info(move)
                        
            # Update the game state based on the current battle situation
            player_pokemon = self.get_pokemon_stats('p1')
            opponent_pokemon = self.get_pokemon_stats('p2')

            self.game_state.player.active_pokemon = self.parse_player_pokemon_stats(player_pokemon)
            self.game_state.opponent.active_pokemon = self.parse_opponent_pokemon_stats(opponent_pokemon)
            
            # Update moves for the active Pokémon
            moves = self.get_move_information()
            self.game_state.player.active_pokemon.moves = moves
            
            # Update opponent's active Pokémon moves with correct information
            if self.game_state.opponent.active_pokemon and self.game_state.opponent.active_pokemon.moves:
                for move in self.game_state.opponent.active_pokemon.moves:
                    self.update_move_info(move)

            # Update revealed Pokémon lists
            self.update_revealed_pokemon(self.game_state.player, self.game_state.player.active_pokemon)
            self.update_revealed_pokemon(self.game_state.opponent, self.game_state.opponent.active_pokemon)
            
            # Check for fainted Pokémon and update revealed_pokemon
            revealed_pokemon_info = self.get_revealed_pokemon()
            parsed_revealed_pokemon = self.parse_revealed_pokemon(revealed_pokemon_info)
            self.update_fainted_pokemon(parsed_revealed_pokemon)
            
            self.game_state.turn += 1
            
        except Exception as e:
            logging.error(f"Error updating game state: {str(e)}")
            # Optionally, you might want to set a flag in the game state to indicate that the update failed
            self.game_state.last_update_failed = True
        else:
            self.game_state.last_update_failed = False
        
    def get_game_state(self) -> GameState:
        # First, update the game state
        self.update_game_state()

        # Then return the current game state
        return self.game_state
        
    
    def start_game(self):
        try:
            time.sleep(2)
            battle_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.button.mainmenu1.big[name='search']"))
            )
            battle_button.click() # Click the battle button
            
            result = self.enter_credentials()  # Use the method to enter both username and password
            print(result)
            
            time.sleep(2)
            
            battle_button.click() # Click the battle button
            
            
            print("Waiting for a match...")
            if self.verify_match_found():
                print("Match found!")
                return "Started the game and found a match"
            else:
                return "Started the game but couldn't verify if a match was found"
            
        except Exception as e:
            return f"Error starting the game: {str(e)}"
        
    def get_observation(self):
        time.sleep(6)
        self.get_game_state()
        return {
            "chat_log": self.game_state.chat_log,
            self.game_state.player.name +" Active Pokemon" : self.game_state.player.active_pokemon,
            self.game_state.opponent.name +" Active Pokemon" : self.game_state.opponent.active_pokemon,
            self.game_state.player.name +" Team Revealed" : self.game_state.player.revealed_pokemon,
            self.game_state.opponent.name +" Team Revealed": self.game_state.opponent.revealed_pokemon,
            "turn": self.game_state.turn
        }

    def reset(self):
        # Reset game state and restart the game driver
        self.game_state = self.initialize_game_state()
        
        # Close the current browser session
        if hasattr(self, 'driver'):
            self.close()
        
        # Set up a new driver
        self.setup_driver()
        
        time.sleep(2)
        
        # Start a new game
        start_result = self.start_game()
        print(f"Game start result: {start_result}")
        
        # Wait for the game to initialize
        time.sleep(5)
        
        # Return the initial observation
        return self.get_observation()

    def step(self, action):
        # TODO: Update game state with action and get observation
        # Execute action
        if action["type"] == "move":
            result = self.select_move(action["move_name"])
            if action["move_name"] == "Terastallize":
                if self.game_state.player.active_pokemon.terastallized:
                    self.game_state.player.can_terastallize = False
                return result
        elif action["type"] == "switch":
            result = self.switch_pokemon(action["switch_name"])
        else:
            raise ValueError(f"Invalid action type: {action['type']}")
        
        # Wait for the turn to complete
        if self.wait_for_turn_completion():
            print("Turn completed")
        else:
            print("Timeout waiting for turn completion")

        time.sleep(1)
        next_observation = self.get_observation()
        #reward = self.calculate_reward(next_observation)
        #done = self.is_game_over()
        #info = {"action_result": result}

        #return next_observation, reward, done, info
        return next_observation, 0, False, {}
    
    def is_waiting_for_opponent(self):
        try:
            return self.driver.find_element(By.XPATH, "//small[contains(text(), 'Waiting for opponent...')]").is_displayed()
        except NoSuchElementException:
            return False
        
    def is_animation_in_progress(self):
        try:
            skip_turn_button = self.driver.find_element(By.XPATH, "//button[@name='skipTurn']")
            if skip_turn_button.is_displayed():
                return True
        except (NoSuchElementException, StaleElementReferenceException):
            pass

        try:
            go_to_end_button = self.driver.find_element(By.XPATH, "//button[@name='goToEnd']")
            if go_to_end_button.is_displayed():
                return True
        except (NoSuchElementException, StaleElementReferenceException):
            pass

        return False
        
    
    def wait_for_turn_completion(self, max_wait_time=180):
        wait_start = time.time()
        while time.time() - wait_start < max_wait_time:
            if not self.is_waiting_for_opponent() and not self.is_animation_in_progress():
                return True
            time.sleep(0.5)
        return False
    
    def select_move(self, move_name):
        try:
            # Find the movemenu
            movemenu = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "movemenu"))
            )
            
            # Find all move buttons
            move_buttons = movemenu.find_elements(By.TAG_NAME, "button")
            
            # Iterate through buttons to find the one with the matching move name
            for button in move_buttons:
                if move_name.lower() == button.get_attribute("data-move").lower():
                    if "disabled" not in button.get_attribute("class"):
                        button.click()
                        return f"Selected move: {move_name}"
                    else:
                        return f"Cannot select {move_name} as it is disabled"
            
            # Check for Terastallize option
            tera_checkbox = movemenu.find_element(By.NAME, "terastallize")
            if move_name.lower() == "terastallize":
                if not tera_checkbox.is_selected():
                    tera_checkbox.click()
                    return f"You have selected to terastallize {self.game_state.player.active_pokemon.name} into the {self.game_state.player.active_pokemon.tera_type} type."
                else:
                    return "Cannot terastallize as you are already terastallized"
            
            return f"Could not find move: {move_name}"
        
        except TimeoutException:
            return "Timeout while waiting for move menu"
        except NoSuchElementException:
            return "Could not find move menu or buttons"
        except Exception as e:
            return f"An error occurred while trying to select move: {str(e)}"

    def switch_pokemon(self, pokemon_name):
        try:
            # Find the switchmenu
            switchmenu = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "switchmenu"))
            )
            
            # Find all switch buttons
            switch_buttons = switchmenu.find_elements(By.TAG_NAME, "button")
            
            # Iterate through buttons to find the one with the matching Pokémon name
            for button in switch_buttons:
                if pokemon_name.lower() in button.text.lower():
                    if "disabled" not in button.get_attribute("class"):
                        button.click()
                        return f"Switched to {pokemon_name}"
                    else:
                        return f"Cannot switch to {pokemon_name} as it is fainted or disabled"
            
            return f"Could not find {pokemon_name} in the switch options"
        
        except TimeoutException:
            return "Timeout while waiting for switch menu"
        except NoSuchElementException:
            return "Could not find switch menu or buttons"
        except Exception as e:
            return f"An error occurred while trying to switch: {str(e)}"

    def calculate_reward(self, observation):
        # Implement reward calculation
        pass

    def render(self):
        # Implement rendering logic
        pass
    

    def get_chat_log(self, turn=None):
        chat_log = self.driver.find_element(By.CSS_SELECTOR, ".battle-log")
        full_log = chat_log.text

        if turn == 0:
            return f"Turn 0\n{full_log}"

        turn_pattern = re.compile(f"Turn {turn}\n(.*?)(?:\nTurn {turn+1}|\Z)", re.DOTALL)
        turn_match = turn_pattern.search(full_log)

        if turn_match:
            return f"Turn {turn}\n{turn_match.group(1).strip()}"
        else:
            return f"Turn {turn}\nNo log found for Turn {turn}"
            
    def update_revealed_pokemon_from_switch_options(self):
        switch_options = self.get_switch_options()
        parsed_pokemon = self.parse_switch_options(switch_options)
        
        for pokemon in parsed_pokemon:
            self.update_revealed_pokemon(self.game_state.player, pokemon)

    def update_fainted_pokemon(self, parsed_revealed_pokemon: Dict[str, List[Pokemon]]):
        for player_key, pokemon_list in parsed_revealed_pokemon.items():
            player = self.game_state.player if player_key == "p1" else self.game_state.opponent
            for revealed_pokemon in pokemon_list:
                self.update_revealed_pokemon_fainted(player, revealed_pokemon, check_fainted=True)

    def update_revealed_pokemon(self, player: Player, active_pokemon: Optional[Pokemon]):
        if not active_pokemon:
            return
        
        # Check if this Pokémon is already in the revealed list
        for revealed in player.revealed_pokemon:
            if revealed.name == active_pokemon.name:
                # Update the existing entry with new information
                revealed.level = active_pokemon.level
                revealed.hp_percentage = active_pokemon.hp_percentage
                revealed.status_effects = active_pokemon.status_effects
                revealed.current_types = active_pokemon.current_types
                revealed.terastallized = active_pokemon.terastallized
                revealed.tera_type = active_pokemon.tera_type
                revealed.base_types = active_pokemon.base_types
                revealed.ability = active_pokemon.ability
                revealed.possible_abilities = active_pokemon.possible_abilities
                revealed.moves = active_pokemon.moves
                revealed.opponent_speed_range = active_pokemon.opponent_speed_range
                return
        
        # If the Pokémon is not in the list, add it
        player.revealed_pokemon.append(active_pokemon)
        
    def update_revealed_pokemon_fainted(self, player: Player, pokemon: Pokemon, check_fainted: bool = False):
        if not pokemon:
            return
        
        # Check if this Pokémon is already in the revealed list
        for revealed in player.revealed_pokemon:
            if revealed.name == pokemon.name:
                # Update the existing entry with new information
                if check_fainted:
                    # Only update fainted status if we're checking for fainted Pokémon
                    if pokemon.hp_percentage == 'fainted':
                        revealed.hp_percentage = 'fainted'
                        revealed.current_hp = 0
                        
    def update_move_info(self, move):
        """Update move information from the JSON file."""
        try:
            with open('C:/Users/JJ/OneDrive/Documents/Coding/LLMAgents/pokemonshowdown/data/pokemon_moves_no_zmoves.json', 'r') as f:
                move_data = json.load(f)
            
            move_name = move.name.lower()
            for move_info in move_data:
                if move_info['name'].lower() == move_name:
                    if move_info['type'] is not None:
                        move.type = move_info['type']
                    if move_info['category'] is not None:
                        move.category = move_info['category']
                    if move_info['power'] is not None:
                        move.power = move_info['power']
                    if move_info['accuracy'] is not None:
                        move.accuracy = move_info['accuracy']
                    if move_info['effect'] is not None:
                        move.description = move_info['effect']
                    return True
            return False
        except Exception as e:
            logging.error(f"Error updating move info: {str(e)}")
            return False
    
    def get_pokemon_stats(self, player='p2'):
        try:
            # Find the statbar
            statbar_class = "rstatbar" if player == 'p1' else "lstatbar"
            statbar = self.driver.find_element(By.CSS_SELECTOR, f'.statbar.{statbar_class}')
            
            # Extract information from the statbar
            pokemon_name = statbar.find_element(By.CSS_SELECTOR, 'strong').text
            hp_text = statbar.find_element(By.CSS_SELECTOR, '.hptext').text
            
            # Extract status effects and boosts
            status_div = statbar.find_element(By.CSS_SELECTOR, '.status')
            status_effects = [span.text for span in status_div.find_elements(By.CSS_SELECTOR, 'span')]
            status_effects = ["None"] if not status_effects else status_effects
            
            # Find the tooltip div and hover to get more details
            tooltip_div = self.driver.find_element(By.CSS_SELECTOR, f'div[data-id="{player}a"]')
            ActionChains(self.driver).move_to_element(tooltip_div).perform()
            
            tooltip = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "tooltip"))
            )
            tooltip_text = tooltip.text
            
            # Check for Terastallized state
            terastallized = "Terastallized" in tooltip_text
            
            # Extract type information
            type_icons = tooltip.find_elements(By.CSS_SELECTOR, ".textaligned-typeicons img")
            #current_types = [type_icons[0].get_attribute("alt")] if type_icons else []
            
            # Extract base types if Terastallized
            base_types = []
            if terastallized:
                base_type_icons = tooltip.find_elements(By.XPATH, ".//small[contains(text(), 'base:')]//img")
                base_types = [icon.get_attribute("alt") for icon in base_type_icons]
            
            # Extract Tera Type if not Terastallized
            tera_type = "Unknown"
            if not terastallized:
                tera_type_element = tooltip.find_elements(By.XPATH, ".//small[contains(text(), 'Tera Type:')]//img")
                if tera_type_element:
                    tera_type = tera_type_element[0].get_attribute("alt")
            
            # Construct the stats string
            stats = f"Pokémon stats for {player}:\n"
            stats += f"Name: {pokemon_name}\n"
            #stats += f"HP: {hp_text}\n"
            stats += f"Status Effects: {', '.join(status_effects)}\n"
            #stats += f"Current Type(s): {', '.join(current_types)}\n"
            if terastallized:
                current_types = [type_icons[0].get_attribute("alt")] if type_icons else []
                stats += f"Terastallized: Yes\n"
                stats += f"Current (Tera) Type: {', '.join(current_types)}\n"
                stats += f"Base Type(s) Before Tera Form: {', '.join(base_types)}\n"
            else:
                current_types = [icon.get_attribute("alt") for icon in type_icons]
                if player != "p2":
                    current_types = current_types[:-1]
                stats += f"Terastallized: No\n"
                stats += f"Tera Type: {tera_type}\n"
                stats += f"Current Type(s): {', '.join(current_types)}\n"
            stats += f"Full Tooltip: {tooltip_text}"
            
            #print(stats)
            
            return stats
        except Exception as e:
            return f"Error getting Pokémon stats: {str(e)}"
   
    def get_move_information(self):
        try:
            battle_controls = self.driver.find_element(By.CSS_SELECTOR, ".battle-controls")
            move_menu = battle_controls.find_element(By.CSS_SELECTOR, ".movemenu")
            move_buttons = move_menu.find_elements(By.CSS_SELECTOR, "button")
            
            moves = []
            for button in move_buttons:
                move_name = button.get_attribute("data-move")
                move_type = button.find_element(By.CSS_SELECTOR, "small.type").text
                pp_text = button.find_element(By.CSS_SELECTOR, "small.pp").text
                current_pp, max_pp = map(int, pp_text.split('/'))
                move_target = button.get_attribute("data-target")
                
                # Hover over the button to get the tooltip
                ActionChains(self.driver).move_to_element(button).perform()
                tooltip = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "tooltip"))
                )
                tooltip_text = tooltip.text
                
                #print(tooltip_text)
                
                # Extract type and category from the tooltip images
                type_category_imgs = tooltip.find_elements(By.CSS_SELECTOR, "img")
                move_type = type_category_imgs[0].get_attribute("alt") if len(type_category_imgs) > 0 else None
                category = type_category_imgs[1].get_attribute("alt") if len(type_category_imgs) > 1 else None
                
                
                power_match = re.search(r"Power: (\d+)", tooltip_text)
                power = int(power_match.group(1)) if power_match else None
                
                accuracy_match = re.search(r"Accuracy: ([\d%]+|can't miss)", tooltip_text)
                accuracy = accuracy_match.group(1) if accuracy_match else None
                
                # Extract description (everything after "Accuracy: X%" line)
                description_parts = tooltip_text.split("Accuracy: ")
                description = description_parts[1].split("\n", 1)[1] if len(description_parts) > 1 else None
                
                
                move = PokemonMove(
                    name=move_name,
                    type=move_type,
                    category=category,
                    power=power,
                    accuracy=accuracy,
                    current_pp=current_pp,
                    max_pp=max_pp,
                    description=description,
                    target=move_target
                )
                moves.append(move)
            
            # Check for Terastallize option
            try:
                tera_label = battle_controls.find_element(By.CSS_SELECTOR, "label.megaevo")
                tera_checkbox = tera_label.find_element(By.CSS_SELECTOR, "input[name='terastallize']")
                tera_type_img = tera_label.find_element(By.CSS_SELECTOR, "img")
                tera_type = tera_type_img.get_attribute("alt")
                
                self.game_state.player.can_terastallize = True
                moves.append(PokemonMove(
                    name="Terastallize",
                    type=tera_type,
                    category="Status",
                    description=f"Terastallize into {tera_type} type",
                    target="self"
                ))
            except NoSuchElementException:
                self.game_state.player.can_terastallize = False
            
            return moves
        except Exception as e:
            print(f"Error getting move information: {str(e)}")
            return []
        
    def get_switch_options(self) -> str:
        try:
            battle_controls = self.driver.find_element(By.CSS_SELECTOR, ".battle-controls")
            switch_menu = battle_controls.find_element(By.CSS_SELECTOR, ".switchmenu")
            switch_info = []
            switch_buttons = switch_menu.find_elements(By.CSS_SELECTOR, "button")
            
            for button in switch_buttons:
                pokemon_name = button.text.split('\n')[0]  # Get the Pokémon name
                
                # Hover over the button to get the tooltip
                ActionChains(self.driver).move_to_element(button).perform()
                tooltip = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "tooltip"))
                )
                tooltip_text = tooltip.text
                
                
                # Extract HP information from tooltip
                hp_match = re.search(r"HP: ([\d.]+)%\s*\(([\d]+)/([\d]+)\)", tooltip_text)
                if hp_match:
                    hp_percentage = str(hp_match.group(1))
                    current_hp = int(hp_match.group(2))
                    max_hp = int(hp_match.group(3))
                    
                    if current_hp > 0:
                        # Check for Terastallized state
                        terastallized = "Terastallized" in tooltip_text
                        
                        # Extract type information
                        type_icons = tooltip.find_elements(By.CSS_SELECTOR, ".textaligned-typeicons img")
                        #current_types = [type_icons[0].get_attribute("alt")] if type_icons else []
                        
                        # Extract base types if Terastallized
                        base_types = []
                        if terastallized:
                            base_type_icons = tooltip.find_elements(By.XPATH, ".//small[contains(text(), 'base:')]//img")
                            base_types = [icon.get_attribute("alt") for icon in base_type_icons]
                        
                        # Extract Tera Type if not Terastallized
                        tera_type = "Unknown"
                        if not terastallized:
                            tera_type_element = tooltip.find_elements(By.XPATH, ".//small[contains(text(), 'Tera Type:')]//img")
                            if tera_type_element:
                                tera_type = tera_type_element[0].get_attribute("alt")
                        
                        pokemon_info = f"Pokémon: {pokemon_name}\n"
                        pokemon_info += f"HP: {current_hp}/{max_hp} ({hp_percentage}%)\n"
                        #pokemon_info += f"Current Type(s): {', '.join(current_types)}\n"
                        if terastallized:
                            current_types = [type_icons[0].get_attribute("alt")] if type_icons else []
                            pokemon_info += f"Terastallized: Yes\n"
                            pokemon_info += f"Current (Tera) Type: {', '.join(current_types)}\n"
                            pokemon_info += f"Base Type(s) Before Tera Form: {', '.join(base_types)}\n"
                        else:
                            current_types = [icon.get_attribute("alt") for icon in type_icons[:-1]]
                            pokemon_info += f"Terastallized: No\n"
                            pokemon_info += f"Tera Type: {tera_type}\n"
                            pokemon_info += f"Current Type(s): {', '.join(current_types)}\n"
                        pokemon_info += f"Tooltip: {tooltip_text}\n"
                        
                        switch_info.append(pokemon_info)
            
            if not switch_info:
                return "No Pokémon available to switch to (all fainted or current Pokémon is the only one left)"
            
            con = "\n".join(switch_info)
            #print(f"Switch options: {con}")
            return con
        except Exception as e:
            return f"Error getting switch options: {str(e)}"
        
    def get_revealed_pokemon(self):
        try:
            revealed_pokemon = {"p1": [], "p2": []}

            for player, bar_class in [("p1", "leftbar"), ("p2", "rightbar")]:
                bar = self.driver.find_element(By.CSS_SELECTOR, f".{bar_class}")
                team_icons = bar.find_elements(By.CSS_SELECTOR, ".teamicons .picon")

                for icon in team_icons:
                    if "pokemonicons-pokeball-sheet" not in icon.get_attribute("style"):
                        pokemon_name = icon.get_attribute("aria-label").split(" (")[0]
                        tooltip_data = icon.get_attribute("data-tooltip")

                        # Hover over the icon to get the tooltip
                        ActionChains(self.driver).move_to_element(icon).perform()
                        tooltip = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "tooltip"))
                        )
                        tooltip_text = tooltip.text

                        # Check for Terastallized state
                        terastallized = "Terastallized" in tooltip_text
                        
                        # Extract type information
                        type_icons = tooltip.find_elements(By.CSS_SELECTOR, ".textaligned-typeicons img")
                        
                        # Extract base types if Terastallized
                        base_types = []
                        if terastallized:
                            base_type_icons = tooltip.find_elements(By.XPATH, ".//small[contains(text(), 'base:')]//img")
                            base_types = [icon.get_attribute("alt") for icon in base_type_icons]
                        
                        # Extract Tera Type if not Terastallized
                        tera_type = "Unknown"
                        if not terastallized:
                            tera_type_element = tooltip.find_elements(By.XPATH, ".//small[contains(text(), 'Tera Type:')]//img")
                            if tera_type_element:
                                tera_type = tera_type_element[0].get_attribute("alt")

                        pokemon_info = f"Pokémon: {pokemon_name}\n"
                        #pokemon_info += f"Current Type(s): {', '.join(current_types)}\n"
                        if terastallized:
                            current_types = [type_icons[0].get_attribute("alt")] if type_icons else []
                            pokemon_info += f"Terastallized: Yes\n"
                            pokemon_info += f"Current (Tera) Type: {', '.join(current_types)}\n"
                            pokemon_info += f"Base Type(s) Before Tera Form: {', '.join(base_types)}\n"
                        else:
                            current_types = [icon.get_attribute("alt") for icon in type_icons]
                            pokemon_info += f"Terastallized: No\n"
                            pokemon_info += f"Tera Type: {tera_type}\n"
                            pokemon_info += f"Current Type(s): {', '.join(current_types)}\n"
                        pokemon_info += f"Tooltip Data: {tooltip_data}\n"
                        pokemon_info += f"Tooltip Text: {tooltip_text}\n"

                        revealed_pokemon[player].append(pokemon_info)

            result = "Revealed Pokémon:\n\n"
            result += "Player 1 (You):\n"
            result += "\n".join(revealed_pokemon["p1"]) if revealed_pokemon["p1"] else "No Pokémon revealed yet.\n"
            result += "\nPlayer 2 (Opponent):\n"
            result += "\n".join(revealed_pokemon["p2"]) if revealed_pokemon["p2"] else "No Pokémon revealed yet.\n"

            #print(result)
            return result

        except Exception as e:
            return f"Error getting revealed Pokémon: {str(e)}"
        
    def parse_player_pokemon_stats(self, stats_string):
        lines = stats_string.split('\n')
        name_level = lines[1].split('Name: ')[1]
        name, level = name_level.split(' L')
        
        status_effects = lines[2].split('Status Effects: ')[1].split(', ')
        if status_effects == ['None']:
            status_effects = []
        
        terastallized = lines[3].split('Terastallized: ')[1] == 'Yes'
        if terastallized:
            current_types = lines[4].split('Current (Tera) Type: ')[1].split(', ')
            tera_type = current_types[0]
            base_types = lines[5].split('Base Type(s) Before Tera Form: ')[1].split(', ')
        else:
            tera_type = lines[4].split('Tera Type: ')[1]
            #if tera_type == 'Unknown':
                #tera_type = None
            current_types = lines[5].split('Current Type(s): ')[1].split(', ')
            base_types = current_types
        
        full_tooltip = '\n'.join(lines[6:])
        
        hp_match = re.search(r"HP: ([\d.]+)%\s*\(([\d]+)/([\d]+)\)", full_tooltip)
        
        if hp_match:
            hp_percentage = str(hp_match.group(1))
            current_hp = int(hp_match.group(2))
            max_hp = int(hp_match.group(3))
        else:
            hp_percentage = None
            current_hp = None
            max_hp = None
        
        possible_abilities = re.search(r"Possible abilities: (.+)", full_tooltip)
        possible_abilities = possible_abilities.group(1).split(', ') if possible_abilities else []
        
        ability = re.search(r"Ability: (.+)", full_tooltip)
        ability = ability.group(1) if ability else None
        
        item = re.search(r"Item: (.+)", full_tooltip)
        item = item.group(1) if item else None
        
        base_stats = re.search(r"Atk (\d+) / Def (\d+) / SpA (\d+) / SpD (\d+) / Spe (\d+)", full_tooltip)
        if base_stats:
            base_stats = {
                'Atk': int(base_stats.group(1)),
                'Def': int(base_stats.group(2)),
                'SpA': int(base_stats.group(3)),
                'SpD': int(base_stats.group(4)),
                'Spe': int(base_stats.group(5))
            }
        else:
            base_stats = None
        
        current_stats = re.search(r"\(After stat modifiers:\)\nAtk (\d+) / Def (\d+) / SpA (\d+) / SpD (\d+) / Spe (\d+)", full_tooltip)
        if current_stats:
            current_stats = {
                'Atk': int(current_stats.group(1)),
                'Def': int(current_stats.group(2)),
                'SpA': int(current_stats.group(3)),
                'SpD': int(current_stats.group(4)),
                'Spe': int(current_stats.group(5))
            }
        else:
            current_stats = base_stats  # If no current stats are provided, use base stats
        
        moves = re.findall(r"• (.+) \((\d+)/(\d+)\)", full_tooltip)
        moves = [PokemonMove(name=move[0], 
                             type=None,
                             category=None,
                             power=None,
                             accuracy=None,
                             current_pp=int(move[1]), 
                             max_pp=int(move[2]),
                             description=None,
                             target=None
                             ) for move in moves]
        
        return Pokemon(
            name=name,
            level=int(level),
            current_hp=current_hp,
            max_hp=max_hp,
            hp_percentage=hp_percentage,
            status_effects=status_effects,
            current_types=current_types,
            base_types=base_types,
            terastallized=terastallized,
            tera_type=tera_type,
            possible_abilities=possible_abilities,
            ability=ability,
            item=item,
            base_stats=base_stats,
            current_stats=current_stats,
            moves=moves
        )

    def parse_opponent_pokemon_stats(self, stats_string):
        lines = stats_string.split('\n')
        name_level = lines[1].split('Name: ')[1]
        name, level = name_level.split(' L')
        
        status_effects = lines[2].split('Status Effects: ')[1].split(', ')
        if status_effects == ['None']:
            status_effects = []
        
        terastallized = lines[3].split('Terastallized: ')[1] == 'Yes'
        
        current_types = []
        base_types = []
        tera_type = None
        
        if terastallized:
            current_types = lines[4].split('Current (Tera) Type: ')[1].split(', ')
            tera_type = current_types[0]
            base_types = lines[5].split('Base Type(s) Before Tera Form: ')[1].split(', ')
        else:
            tera_type = lines[4].split('Tera Type: ')[1]
            #if tera_type == 'Unknown':
                #tera_type = None
            current_types = lines[5].split('Current Type(s): ')[1].split(', ')
            base_types = current_types
        
        full_tooltip = '\n'.join(lines[6:])
        
        hp_match = re.search(r"HP: ([\d.]+)%", full_tooltip)
        hp_percentage = str(hp_match.group(1)) if hp_match else None
        
        possible_abilities = re.search(r"Possible abilities: (.+)", full_tooltip)
        possible_abilities = possible_abilities.group(1).split(', ') if possible_abilities else []
        
        if len(possible_abilities) == 1:
            ability = possible_abilities[0]
        else:
            ability = re.search(r"Ability: (\w+)", full_tooltip)
            ability = ability.group(1) if ability else None
        
        speed_range = re.search(r"Spe (\d+) to (\d+)", full_tooltip)
        opponent_speed_range = None
        if speed_range:
            opponent_speed_range = (int(speed_range.group(1)), int(speed_range.group(2)))
            
        moves = re.findall(r"• (.+) \((\d+)/(\d+)\)", full_tooltip)
        moves = [PokemonMove(name=move[0], 
                             type=None,
                             category=None,
                             power=None,
                             accuracy=None,
                             current_pp=int(move[1]), 
                             max_pp=int(move[2]),
                             description=None,
                             target=None
                             ) for move in moves]
        
        return Pokemon(
            name=name,
            level=int(level),
            hp_percentage=hp_percentage,
            status_effects=status_effects,
            current_types=current_types,
            terastallized=terastallized,
            tera_type=tera_type,
            base_types=base_types,
            ability=ability,
            possible_abilities=possible_abilities,
            opponent_speed_range=opponent_speed_range,
            moves=moves
        )

    def parse_revealed_pokemon(self, revealed_string: str) -> Dict[str, List[Pokemon]]:
        revealed_pokemon = {"p1": [], "p2": []}
        current_player = None
        current_pokemon_info = []

        for line in revealed_string.split('\n'):
            if line.startswith("Player 1 (You):"):
                current_player = "p1"
            elif line.startswith("Player 2 (Opponent):"):
                current_player = "p2"
            elif line.startswith("Pokémon:"):
                if current_pokemon_info:
                    pokemon = self._create_pokemon_from_info(current_pokemon_info, current_player)
                    if pokemon:
                        revealed_pokemon[current_player].append(pokemon)
                current_pokemon_info = [line]
            elif line.strip():
                current_pokemon_info.append(line)

        # Add the last Pokémon
        if current_pokemon_info:
            pokemon = self._create_pokemon_from_info(current_pokemon_info, current_player)
            if pokemon:
                revealed_pokemon[current_player].append(pokemon)

        return revealed_pokemon

    def _create_pokemon_from_info(self, info_lines: List[str], player: str) -> Optional[Pokemon]:
        if not info_lines:
            return None

        pokemon_data = {}
        for line in info_lines:
            if ': ' in line:
                key, value = line.split(': ', 1)
                if key == 'Tooltip Text':
                    # Include all remaining lines for Tooltip Text
                    value += '\n' + '\n'.join(info_lines[info_lines.index(line)+1:])
                pokemon_data[key] = value

        if 'Pokémon' not in pokemon_data:
            return None

        name = pokemon_data['Pokémon']
        terastallized = pokemon_data.get('Terastallized', 'No') == 'Yes'
        if terastallized:
            tera_type = pokemon_data.get('Current (Tera) Type')
            current_types = tera_type
            base_types_match = re.search(r"Base Type\(s\) Before Tera Form: (.+)", "\n".join(info_lines))
            if base_types_match:
                base_types = base_types_match.group(1).split(", ")
        else:
            tera_type = pokemon_data.get('Tera Type')
            current_types = pokemon_data.get('Current Type(s)', '').split(', ')
            base_types = current_types
            
        tooltip_text = pokemon_data.get('Tooltip Text', '')
        
        # Parse information from tooltip_text
        tooltip_lines = tooltip_text.split('\n')

        # Extract additional information from tooltip_text
        level_match = re.search(r"L(\d+)", tooltip_lines[0])
        level = int(level_match.group(1)) if level_match else None

        hp_match = re.search(r"HP: ([\d.]+)%", tooltip_text)
        fainted_match = re.search(r"HP: \(fainted\)", tooltip_text)
        if fainted_match:
            hp_percentage = "fainted"
        elif hp_match:
            hp_percentage = str(hp_match.group(1))
        else:
            hp_percentage = None

        status_effects = []
        for status in ['BRN', 'PSN', 'PAR', 'FRZ', 'SLP']:
            if status in tooltip_text:
                status_effects.append(status)

        # Extract abilities
        ability = None
        possible_abilities = []
        if player == "p2":
            possible_abilities_match = re.search(r"Possible abilities: (.+)", tooltip_text)
            possible_abilities = possible_abilities_match.group(1).split(", ") if possible_abilities_match else []
            if len(possible_abilities) == 1:
                ability = possible_abilities[0]

        # Extract speed range for opponent Pokémon
        opponent_speed_range = None
        if player == "p2":
            speed_range_match = re.search(r"Spe (\d+) to (\d+)", tooltip_text)
            opponent_speed_range = (int(speed_range_match.group(1)), int(speed_range_match.group(2))) if speed_range_match else None


        moves = re.findall(r"• (.+) \((\d+)/(\d+)\)", tooltip_text)
        moves = [PokemonMove(name=move[0], 
                             type=None,
                             category=None,
                             power=None,
                             accuracy=None,
                             current_pp=int(move[1]), 
                             max_pp=int(move[2]),
                             description=None,
                             target=None
                             ) for move in moves]


        return Pokemon(
            name=name,
            level=level,
            hp_percentage=hp_percentage,
            status_effects=status_effects,
            current_types=current_types,
            terastallized=terastallized,
            tera_type=tera_type,
            base_types=base_types,
            possible_abilities=possible_abilities,
            ability=ability,
            opponent_speed_range=opponent_speed_range,
            moves=moves
        )
        
    def parse_switch_options(self, switch_options: str) -> List[Pokemon]:
        pokemon_list = []
        pokemon_info_list = switch_options.split('\n\n')
        
        for pokemon_info in pokemon_info_list:
            lines = pokemon_info.split('\n')
            name = lines[0].split(': ')[1]
            
            hp_info = lines[1].split(': ')[1]
            current_hp, max_hp = map(int, re.search(r"(\d+)/(\d+)", hp_info).groups())
            hp_percentage = re.search(r"\((\d+\.\d+)%\)", hp_info).group(1)
            
            terastallized = lines[2].split(': ')[1] == 'Yes'
            tera_type = lines[3].split(': ')[1]
            current_types = lines[4].split(': ')[1].split(', ')
            
            tooltip = '\n'.join(lines[5:])
            
            level_match = re.search(r"L(\d+)", tooltip)
            level = int(level_match.group(1)) if level_match else None
            
            #print(f"Tooltip for {name}:")
            #print(tooltip)
            #print("---")

            ability_item_match = re.search(r"Ability:\s*(.+?)\s*/\s*Item:\s*(.+?)(?=\s*$|\s*\n)", tooltip, re.IGNORECASE | re.DOTALL)
            if ability_item_match:
                ability = ability_item_match.group(1).strip()
                item = ability_item_match.group(2).strip()
                #print(f"Matched - Ability: {ability}, Item: {item}")
            else:
                #print("No match found for ability/item pattern")
                ability = None
                item = None
            
            stats_match = re.search(r"Atk (\d+) / Def (\d+) / SpA (\d+) / SpD (\d+) / Spe (\d+)", tooltip)
            base_stats = {
                'Atk': int(stats_match.group(1)),
                'Def': int(stats_match.group(2)),
                'SpA': int(stats_match.group(3)),
                'SpD': int(stats_match.group(4)),
                'Spe': int(stats_match.group(5))
            } if stats_match else None
            
            moves = re.findall(r"• (.+)", tooltip)
            pokemon_moves = [PokemonMove(name=move) for move in moves]
            
            pokemon = Pokemon(
                name=name,
                level=level,
                current_hp=current_hp,
                max_hp=max_hp,
                hp_percentage=hp_percentage,
                #status_effects=[],  # We don't have this information from switch options
                current_types=current_types,
                base_types=current_types if not terastallized else [],
                terastallized=terastallized,
                tera_type=tera_type,
                possible_abilities=[ability] if ability else [],
                ability=ability,
                item=item,
                base_stats=base_stats,
                current_stats=base_stats,  # We don't have current stats, so use base stats
                moves=pokemon_moves
            )
            pokemon_list.append(pokemon)
        
        return pokemon_list

    def close(self):
        self.driver.quit()


if __name__ == "__main__":
    # Example usage of the PokemonShowdownEnv class
    username = "Poke214915"
    password = "LLMAgent1234"
    
    # Create an instance of the environment
    env = PokemonShowdownEnv(username, password)
    
    try:
        # Start the game
        env.start_game()
        time.sleep(5)
        # Main game loop
        while True:
            # Get the current observation
            observation = env.get_observation()
            print("Current game state:", observation)
            while True:
                time.sleep(1)
            
            # Here you would typically decide on an action based on the observation
            # For this example, we'll just use a dummy action
            #action = {"type": "move", "move_number": "1"}
            
            # Take a step in the environment
            #next_observation, reward, done, info = env.step(action)
            
            #print("Action taken:", action)
            #print("Reward:", reward)
            #print("Action result:", info["action_result"])
            
            #if done:
            #    print("Game over!")
            #    break
    
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    
    finally:
        # Always close the environment to clean up resources
        env.close()

