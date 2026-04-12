"""Django management command wrapping starships.legacy_import.

    python manage.py import_legacy_fleets              # all agencies
    python manage.py import_legacy_fleets --dry-run    # preview
    python manage.py import_legacy_fleets --agency 3   # single agency
    python manage.py import_legacy_fleets --force      # re-run even if tagged
"""

from django.core.management.base import BaseCommand

from starships.legacy_import import import_all_legacy_fleets


class Command(BaseCommand):
    help = "Import legacy Agency.fleet JSON blobs into real Starship records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Compute the import plan without writing anything.",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Re-import even agencies that already have legacy-tagged ships.",
        )
        parser.add_argument(
            "--agency", type=int, default=None,
            help="Import only the agency with this ID.",
        )

    def handle(self, *args, **options):
        result = import_all_legacy_fleets(
            dry_run=options["dry_run"],
            force=options["force"],
            agency_id=options["agency"],
        )
        totals = result["totals"]
        tag = " [DRY RUN]" if result["dry_run"] else ""

        self.stdout.write(self.style.HTTP_INFO(f"Legacy fleet import{tag}"))
        self.stdout.write(f"  Agencies processed : {totals['agencies_processed']}")
        self.stdout.write(f"  Agencies skipped   : {totals['agencies_skipped']}")
        self.stdout.write(f"  Entries processed  : {totals['entries_processed']}")
        self.stdout.write(f"  Classes created    : {totals['classes_created']}")
        self.stdout.write(f"  Classes reused     : {totals['classes_reused']}")
        self.stdout.write(f"  Ships created      : {totals['ships_created']}")
        self.stdout.write(f"  Warnings           : {totals['warnings']}")
        self.stdout.write(f"  Errors             : {totals['errors']}")

        for report in result["reports"]:
            if report["skipped"] and not report["warnings"] and not report["errors"]:
                continue
            self.stdout.write("")
            self.stdout.write(self.style.NOTICE(
                f"[{report['agency_name']}]"
                + (" SKIPPED" if report["skipped"] else "")
            ))
            for w in report["warnings"]:
                self.stdout.write(self.style.WARNING(f"  warn: {w}"))
            for e in report["errors"]:
                self.stdout.write(self.style.ERROR(f"  error: {e}"))
            if not report["skipped"]:
                self.stdout.write(
                    f"  entries={report['processed_entries']} "
                    f"classes_new={report['created_classes']} "
                    f"classes_reused={report['reused_classes']} "
                    f"ships={report['created_ships']}"
                )
