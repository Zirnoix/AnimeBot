import requests

def query_anilist(query, variables=None):
    url = "https://graphql.anilist.co"
    response = requests.post(url, json={"query": query, "variables": variables})
    if response.status_code != 200:
        raise Exception(f"Erreur AniList: {response.status_code}")
    return response.json()

def get_upcoming_episodes(username):
    query = """
    query ($userName: String) {
      MediaListCollection(userName: $userName, type: ANIME, status_in: [CURRENT, PLANNING]) {
        lists {
          entries {
            media {
              id
              title {
                romaji
              }
              nextAiringEpisode {
                airingAt
                episode
              }
              genres
            }
          }
        }
      }
    }
    """
    result = query_anilist(query, {"userName": username})
    data = result["data"]["MediaListCollection"]["lists"]
    episodes = []
    for lst in data:
        for entry in lst["entries"]:
            media = entry["media"]
            next_ep = media.get("nextAiringEpisode")
            if next_ep:
                episodes.append({
                    "title": media["title"]["romaji"],
                    "airingAt": next_ep["airingAt"],
                    "episode": next_ep["episode"],
                    "genres": media["genres"]
                })
    return episodes