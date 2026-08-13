param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z_][A-Za-z0-9_]{0,62}$')]
    [string]$TargetDb,
    [switch]$Resume
)

$ErrorActionPreference = 'Stop'
$realDb = 'swiss_garden_jobs'
if ($TargetDb -eq $realDb -or $TargetDb -eq 'swiss_garden_jobs_gate011e_contract') {
    throw 'TargetDb must be a new isolated database'
}
$envFile = '..\gate011f-clean\.env'
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable(
            $matches[1].Trim(), $matches[2].Trim().Trim('"'), 'Process'
        )
    }
}
$package = '.gate011gc1-artifacts\review-authority-lineage-corrected-v0.1.json'
$registry = 'docs\day0\gate_011g_c1_review_authority_registry_v0_1.json'
$transcript = ".gate011gc1-artifacts\audit-correction-acceptance-$TargetDb.txt"

if (-not $Resume) {
    python scripts\gate011g_c1_clone_database.py --source $realDb --target $TargetDb
    if ($LASTEXITCODE -ne 0) { throw 'Isolated database clone failed' }
}
$env:POSTGRES_DB = $TargetDb
Start-Transcript -Path $transcript -Force
try {
    python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Existing-copy migration failed' }
    python manage.py import_reference_data
    if ($LASTEXITCODE -ne 0) { throw 'First reference import failed' }
    python manage.py import_reference_data
    if ($LASTEXITCODE -ne 0) { throw 'Second reference import failed' }
    python manage.py import_review_authority_lineage --package $package --registry $registry --dry-run
    if ($LASTEXITCODE -ne 0) { throw 'Package preflight failed' }
    python manage.py import_review_authority_lineage --package $package --registry $registry
    if ($LASTEXITCODE -ne 0) { throw 'First package import failed' }
    python manage.py import_review_authority_lineage --package $package --registry $registry
    if ($LASTEXITCODE -ne 0) { throw 'Second package import failed' }

    $code = @"
import json
from django.core.management import call_command
from django.utils import timezone
from core.models import ReviewAuthorityLineageImport
from observations.models import GreenRelevanceReviewDecision, GreenRelevanceReviewDecisionApplication
from vacancies.models import DedupDecision, DedupReviewDecisionApplication, DedupRun
from vacancies.engine import run_deduplication
from premium_segments.classifier import run_classification
from premium_segments.models import PremiumSegmentRun
from dashboard.services import build_dashboard_snapshot
from dashboard.models import DashboardSnapshot
from day0.services import assess_day0_readiness, readiness_summary
from day0.models import Day0ReadinessAssessment

before_green = GreenRelevanceReviewDecisionApplication.objects.count()
before_dedup = DedupReviewDecisionApplication.objects.count()
call_command('apply_review_continuity', target_as_of=timezone.now())
after_green = GreenRelevanceReviewDecisionApplication.objects.count()
provisional_cutoff = timezone.now()
provisional_dedup, provisional_reused = run_deduplication(provisional_cutoff)
after_dedup = DedupReviewDecisionApplication.objects.count()
if after_dedup > before_dedup:
    final_cutoff = timezone.now()
    dedup, dedup_reused = run_deduplication(final_cutoff)
else:
    final_cutoff = provisional_cutoff
    dedup, dedup_reused = provisional_dedup, provisional_reused
premium, premium_reused = run_classification(final_cutoff)
dashboard, dashboard_reused = build_dashboard_snapshot(as_of=final_cutoff, dedup_run=dedup, premium_run=premium)
readiness, readiness_reused = assess_day0_readiness(as_of=final_cutoff, dedup_run=dedup, premium_run=premium, dashboard_snapshot=dashboard)
replay_dedup, replay_dedup_reused = run_deduplication(final_cutoff)
replay_premium, replay_premium_reused = run_classification(final_cutoff)
replay_dashboard, replay_dashboard_reused = build_dashboard_snapshot(as_of=final_cutoff, dedup_run=replay_dedup, premium_run=replay_premium)
replay_readiness, replay_readiness_reused = assess_day0_readiness(as_of=final_cutoff, dedup_run=replay_dedup, premium_run=replay_premium, dashboard_snapshot=replay_dashboard)
batch = ReviewAuthorityLineageImport.objects.get()
result = {
    'as_of': final_cutoff.isoformat(),
    'lineage_batch': str(batch.pk),
    'replicated_at': batch.replicated_at.isoformat(),
    'package_sha256': batch.package_sha256,
    'source_snapshot_fingerprint': batch.source_snapshot_fingerprint,
    'green_human_decisions': GreenRelevanceReviewDecision.objects.count(),
    'human_dedup_decisions': DedupDecision.objects.filter(method='HUMAN').count(),
    'green_applications_before': before_green,
    'green_applications_after': after_green,
    'dedup_applications_before': before_dedup,
    'dedup_applications_after': after_dedup,
    'dedup': {'id': str(dedup.pk), 'fingerprint': dedup.input_fingerprint, 'replay_id': str(replay_dedup.pk), 'replay_reused': replay_dedup_reused, 'artifacts': DedupRun.objects.filter(input_fingerprint=dedup.input_fingerprint).count()},
    'premium': {'id': str(premium.pk), 'fingerprint': premium.input_fingerprint, 'replay_id': str(replay_premium.pk), 'replay_reused': replay_premium_reused, 'artifacts': PremiumSegmentRun.objects.filter(input_fingerprint=premium.input_fingerprint).count()},
    'dashboard': {'id': str(dashboard.pk), 'fingerprint': dashboard.input_fingerprint, 'replay_id': str(replay_dashboard.pk), 'replay_reused': replay_dashboard_reused, 'artifacts': DashboardSnapshot.objects.filter(input_fingerprint=dashboard.input_fingerprint).count()},
    'readiness': {'id': str(readiness.pk), 'fingerprint': readiness.input_fingerprint, 'replay_id': str(replay_readiness.pk), 'replay_reused': replay_readiness_reused, 'artifacts': Day0ReadinessAssessment.objects.filter(input_fingerprint=readiness.input_fingerprint).count(), 'summary': readiness_summary(readiness, readiness_reused)},
}
assert result['green_human_decisions'] == 55
assert result['human_dedup_decisions'] == 1
assert ReviewAuthorityLineageImport.objects.count() == 1
for layer in ('dedup', 'premium', 'dashboard', 'readiness'):
    assert result[layer]['id'] == result[layer]['replay_id']
    assert result[layer]['artifacts'] == 1
print('C1_AUDIT_CORRECTION_ACCEPTANCE=' + json.dumps(result, sort_keys=True, default=str))
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code))
    python manage.py shell --no-startup -c "import base64;exec(base64.b64decode('$encoded'))"
    if ($LASTEXITCODE -ne 0) { throw 'Corrected continuity/PIT acceptance failed' }
}
finally {
    Stop-Transcript
}
Write-Output "Acceptance transcript: $transcript"
