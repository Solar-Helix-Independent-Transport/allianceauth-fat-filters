from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from fatfilters.models import FATInTimePeriod
from afat.models.smart_filter import FatsInTimeFilter


class Command(BaseCommand):
    help = "Migrate fatfilters FATInTimePeriod records to afat FatsInTimeFilter"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete source FATInTimePeriod records after successful migration",
        )

    def handle(self, *args, **options):
        filters = FATInTimePeriod.objects.prefetch_related(
            "fleet_type_filter", "ship_names"
        ).all()

        if not filters.exists():
            self.stdout.write("No FATInTimePeriod filters found.")
            return

        id_map = {}  # old FATInTimePeriod pk -> new FatsInTimeFilter instance
        migrated = 0
        skipped = 0

        for src in filters:
            existing = FatsInTimeFilter.objects.filter(
                name=src.name, description=src.description
            ).first()

            if existing:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping '{src.name}' — already exists as FatsInTimeFilter (id={existing.pk})"
                    )
                )
                id_map[src.pk] = existing
                skipped += 1
                continue

            dst = FatsInTimeFilter.objects.create(
                name=src.name,
                description=src.description,
                days=src.days,
                fats_needed=src.fats_needed,
            )
            dst.fleet_types.set(src.fleet_type_filter.all())
            dst.ship_classes.set(src.ship_names.all())

            self.stdout.write(
                self.style.SUCCESS(
                    f"Migrated '{src.name}' (id={src.pk}) -> FatsInTimeFilter (id={dst.pk})"
                )
            )
            id_map[src.pk] = dst
            migrated += 1

        self.stdout.write(f"\nDone: {migrated} migrated, {skipped} skipped.")

        if id_map:
            old_ct = ContentType.objects.get_for_model(FATInTimePeriod)
            new_ct = ContentType.objects.get_for_model(FatsInTimeFilter)
            self._update_secure_groups(id_map, old_ct, new_ct)
            self._update_auth_reports(id_map, old_ct, new_ct)
            self._update_hrapps(id_map, old_ct, new_ct)

        if options["delete"]:
            FATInTimePeriod.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(
                    f"Deleted {len(id_map)} source FATInTimePeriod record(s)."
                )
            )

    def _update_secure_groups(self, id_map, old_ct, new_ct):
        try:
            SmartFilter = apps.get_model("securegroups", "SmartFilter")
            SmartGroup = apps.get_model("securegroups", "SmartGroup")
            GracePeriodRecord = apps.get_model("securegroups", "GracePeriodRecord")
            PendingNotification = apps.get_model("securegroups", "PendingNotification")
        except LookupError:
            return

        self.stdout.write("\nUpdating SecureGroups...")
        total = 0

        for old_id, new_obj in id_map.items():
            new_sf = SmartFilter.objects.filter(content_type=new_ct, object_id=new_obj.pk).first()
            if new_sf is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"  No SmartFilter binding for FatsInTimeFilter '{new_obj.name}' — skipping"
                    )
                )
                continue

            for old_sf in SmartFilter.objects.filter(content_type=old_ct, object_id=old_id):
                GracePeriodRecord.objects.filter(grace_filter=old_sf).update(grace_filter=new_sf)
                PendingNotification.objects.filter(filter=old_sf).update(filter=new_sf)

                for group in SmartGroup.objects.filter(filters=old_sf):
                    group.filters.remove(old_sf)
                    group.filters.add(new_sf)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  SmartGroup '{group}': replaced filter with '{new_obj.name}'"
                        )
                    )
                    total += 1

                old_sf.delete()

        if not total:
            self.stdout.write("  No SmartGroup references found.")

    def _update_auth_reports(self, id_map, old_ct, new_ct):
        try:
            ReportDataSource = apps.get_model("authstats", "ReportDataSource")
            ReportDataThrough = apps.get_model("authstats", "ReportDataThrough")
        except LookupError:
            return

        self.stdout.write("\nUpdating Auth Reports...")
        total = 0

        for old_id, new_obj in id_map.items():
            new_rds = ReportDataSource.objects.filter(content_type=new_ct, object_id=new_obj.pk).first()
            if new_rds is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"  No ReportDataSource binding for FatsInTimeFilter '{new_obj.name}' — skipping"
                    )
                )
                continue

            for old_rds in ReportDataSource.objects.filter(content_type=old_ct, object_id=old_id):
                throughs = ReportDataThrough.objects.filter(report_Data_source=old_rds)
                report_names = list(throughs.values_list("report__name", flat=True))
                throughs.update(report_Data_source=new_rds)
                old_rds.delete()

                for name in report_names:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  Report '{name}': replaced filter with '{new_obj.name}'"
                        )
                    )
                    total += 1

        if not total:
            self.stdout.write("  No Report references found.")

    def _update_hrapps(self, id_map, old_ct, new_ct):
        try:
            FilterDataSource = apps.get_model("hrapps", "FilterDataSource")
            ApplicationForm = apps.get_model("hrapps", "ApplicationForm")
        except LookupError:
            return

        self.stdout.write("\nUpdating HR Apps...")
        total = 0

        for old_id, new_obj in id_map.items():
            new_fds = FilterDataSource.objects.filter(content_type=new_ct, object_id=new_obj.pk).first()
            if new_fds is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"  No FilterDataSource binding for FatsInTimeFilter '{new_obj.name}' — skipping"
                    )
                )
                continue

            for old_fds in FilterDataSource.objects.filter(content_type=old_ct, object_id=old_id):
                for form in ApplicationForm.objects.filter(filters=old_fds):
                    form.filters.remove(old_fds)
                    form.filters.add(new_fds)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ApplicationForm '{form}': replaced filter with '{new_obj.name}'"
                        )
                    )
                    total += 1

                old_fds.delete()

        if not total:
            self.stdout.write("  No ApplicationForm references found.")
