def main() -> None:
    from wisprtypr.app import Application
    from wisprtypr.runtime import configure_process_metadata

    configure_process_metadata()
    Application().run()
