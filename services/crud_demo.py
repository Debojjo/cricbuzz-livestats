"""A guided tour of the CRUD module on your real database.

    python -m services.crud_demo

It creates ONE manual player, reads, updates and deletes it again, and shows
what happens when you try something the rules forbid. It removes everything it
creates, so your data is unchanged afterwards.
"""

from services import crud_service as crud
from utils.validators import ValidationError


def attempt(label: str, action):
    """Run ``action`` and print the result or the friendly error."""
    try:
        result = action()
        print(f"  OK      {label}: {result}")
        return result
    except (crud.CrudError, ValidationError) as exc:
        print(f"  BLOCKED {label}: {exc}")
        return None


def main() -> None:
    """Run the tour."""
    print("\n1. CREATE")
    new_id = attempt(
        "create player",
        lambda: crud.create_player(
            {
                "full_name": "Demo Player",
                "country": "Demoland",
                "playing_role": "Batsman",
                "date_of_birth": "2001-05-17",
            }
        ),
    )
    attempt(
        "create with bad input",
        lambda: crud.create_player({"full_name": "", "playing_role": "Astronaut"}),
    )

    print("\n2. READ")
    attempt("get player", lambda: crud.get_player(new_id)["full_name"])
    attempt(
        "search 'Demo'",
        lambda: [r["full_name"] for r in crud.list_players(search="Demo")["rows"]],
    )

    print("\n3. UPDATE")
    attempt(
        "change role",
        lambda: crud.update_player(new_id, {"playing_role": "Bowler"})["playing_role"],
    )
    attempt(
        "edit a real API player (1413)",
        lambda: crud.update_player(1413, {"country": "X"}),
    )

    print("\n4. DELETE")
    attempt("delete a real API player (1413)", lambda: crud.delete_player(1413))
    attempt("delete the demo player", lambda: crud.delete_player(new_id))
    attempt("player is gone", lambda: crud.get_player(new_id))
    print("\nDone: the demo player was removed again.\n")


if __name__ == "__main__":
    main()
