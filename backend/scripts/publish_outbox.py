"""Run from backend/: python -m scripts.publish_outbox --once OR --loop"""
import argparse
import time

from app.services.event_streaming import new_producer, publish_batch


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--loop", action="store_true")
    args = parser.parse_args()

    producer = new_producer()
    try:
        while True:
            count = publish_batch(producer)
            print(f"Outbox: {count} event(s) delivered")
            if args.once:
                break
            time.sleep(3)
    except KeyboardInterrupt:
        print("Publisher stopped")


if __name__ == "__main__":
    main()
