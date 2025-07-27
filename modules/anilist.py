import requests

API_URL = "https://graphql.anilist.co"

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

def run_query(query, variables=None):
    response = requests.post(API_URL, json={"query": query, "variables": variables}, headers=HEADERS)
    if response.status_code != 200:
        print("Erreur API Anilist:", response.text)
        return None
    return response.json()

def get_random_anime():
    import random
    page = random.randint(1, 500)
    query = '''
    query ($page: Int) {
      Page(page: $page, perPage: 1) {
        media(type: ANIME, isAdult: false, sort: SCORE_DESC) {
          id
          title {
            romaji
            english
            native
          }
          description(asHtml: false)
          coverImage {
            large
          }
        }
      }
    }
    '''
    data = run_query(query, {"page": page})
    if data:
        return data["data"]["Page"]["media"][0]
    return None

def get_upcoming_episodes(user_anilist_id):
    query = '''
    query ($userId: Int) {
      MediaListCollection(userId: $userId, type: ANIME, status_in: [CURRENT, PLANNING]) {
        lists {
          entries {
            media {
              title {
                romaji
              }
              nextAiringEpisode {
                airingAt
                episode
              }
            }
          }
        }
      }
    }
    '''
    data = run_query(query, {"userId": user_anilist_id})
    if not data:
        return []
    episodes = []
    for lst in data["data"]["MediaListCollection"]["lists"]:
        for entry in lst["entries"]:
            media = entry["media"]
            next_ep = media.get("nextAiringEpisode")
            if next_ep:
                episodes.append({
                    "title": media["title"]["romaji"],
                    "airingAt": next_ep["airingAt"],
                    "episode": next_ep["episode"]
                })
    return episodes
