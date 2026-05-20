import argparse


def seed(clear: bool = False) -> None:
    if clear:
        print("Ticketing seed no longer clears data; match ticketing data lives in the monolith.")
        return
    print("Ticketing seed skipped; match ticketing data lives in the monolith.")


def main():
    parser = argparse.ArgumentParser(
        description="Ticketing data is sourced from the Django monolith."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete local bookings.",
    )
    parser.add_argument(
        "--inventory-only",
        action="store_true",
        help="Compatibility flag; inventory is no longer seeded locally.",
    )
    args = parser.parse_args()
    seed(clear=args.clear)


if __name__ == "__main__":
    main()
