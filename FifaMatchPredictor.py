import os
import openai
import json
from datetime import datetime
import yaml

client = openai.OpenAI()

# Create constant for whichever model you want to use, normally better to keep in a separate file
MODEL_GPT_5_5 = "gpt-5.5"
MODEL_GPT_4_O_MINI = "gpt-4o-mini"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXT_FILE = os.path.join(BASE_DIR, "context_store.json")
PROMPTS_FILE = os.path.join(BASE_DIR, "prompts.yaml")

with open(PROMPTS_FILE) as f:
    prompts = yaml.safe_load(f)

def load_context():
    if os.path.exists(CONTEXT_FILE):
        with open(CONTEXT_FILE, "r") as f:
            return json.load(f)
    return {"topics": {}, "last_updated": None}

def save_context(context):
    context["last_updated"] = datetime.now().isoformat()
    with open(CONTEXT_FILE, "w") as f:
        json.dump(context, f, indent=2)

def deep_merge(old, new):
    """Recursively merge new dict into old dict."""
    for key, value in new.items():
        if key in old and isinstance(old[key], dict) and isinstance(value, dict):
            deep_merge(old[key], value)
        else:
            old[key] = value
    return old

def update_context(context, topic, new_data):

    if topic not in context["topics"]:
        context["topics"][topic] = {}
    deep_merge(context["topics"][topic], new_data)

    return context

def build_prompt(user_query, context, topic):
    existing = context["topics"]
    
    existing_summary = json.dumps(existing, indent=2) if existing else "No prior data on this topic."

    return f"""Here is what we know so far on this topic ("{topic}"):
        {existing_summary}

        Now do the following:
        {user_query}

        If existing information looks outdated, search for updates and return ONLY 
        the fields that changed or are new, as a JSON object matching the same structure 
        as above (or creating new keys if this is new information)."""
        
def build_insight_prompt(user_query, context, topic):
    existing = context["topics"]
    
    existing_summary = json.dumps(existing, indent=2) if existing else "No prior data on this topic."
    
    # We have asked our model to first see if our knowledge base is capable of answering the question by itself,
    # if so, just use the data present, if not to update by using the tools we have provided (web-search in this case).
    # This way, we can make it so we dont use too many tokens to keep fetching the information we already have fetched once before.
    return f"""Here is what we know so far on this topic ("{topic}"):
        {existing_summary}

        Now do the following:
        {user_query}

        Base your answer on the data above. If something is missing or null, you can search 
the web to fill gaps, but clearly note when you're estimating vs. using known data. Also mention probability 
of assist by top 2-3 players, how many goals do you think easy team might try to make,
who do you think might be the player trying to make the goal, probability of red or yellow card and suspension
by which player - mention only top 2 for each team"""
        
def getResponse(query,model,topic=None):
    
    context = load_context()
    
    prompt = build_prompt(query, context, topic)

# can use filetrs to restrict the web search. In our search we have been passing 4o-mini
# which doesn't allow filters, so have not used it here, but that logic can be added.
    response = client.responses.create(
        model=model,
        input=prompt,
        max_output_tokens=4000,
        tools=[{"type": "web_search"}]
    )
    try:
        new_data = json.loads(response.output_text)
        context = update_context(context, topic, new_data)
        save_context(context)
        print(f"[{topic}] Saved topics:", list(context["topics"].keys()))
    except json.JSONDecodeError as e:
        print(f"[{topic}] JSON parse failed: {e}")
        print(f"[{topic}] Raw response: {response.output_text}")
    
    return response

def getInsight(query, model, topic=None):
    context = load_context()
    prompt = build_insight_prompt(query, context, topic)

    response = client.responses.create(
        model=model,
        input=prompt,
        max_output_tokens=4000,
        tools=[{"type": "web_search"}]
    )

    return response.output_text

initial_setup_query = prompts["initial_setup_template"]


query = prompts["match_outcome_query_template"]


# initial setup for the upcoming matches, scrape the web to generate a knowledge base... kind of
team_list = ["USA", "Paraguay"]
for team in team_list:
    # Used to update the knowledge base, don't relly need to use the returned values, 
    # can be printed for debug
    getResponse(initial_setup_query.format(team_name=team), MODEL_GPT_4_O_MINI, team)

# Use prompt from prompts.yaml, can similarly have prompts.json
print(getResponse(query.format(team1="Bosnia and Herzegovina", team2="Canada"), MODEL_GPT_4_O_MINI, "Bosnia and Herzegovina vs Canada").output_text)

# Just conversationally try to ask question. It will look into the database, if information is not found or
# feels outdated it will scrape the web again to update the information and then answer the question
print(getInsight("up-to-date player fitness and additional contextual information", MODEL_GPT_4_O_MINI, "Bosnia and Herzegovina vs Canada"))
