# Snakemake BCL Conversion Pipeline

Automated workflow for Illumina (MiSeq i100 / NovaSeqX) sequencing data processing, quality control, and report generation.

## Workflow Diagram

![Workflow Rule Graph](rulegraph.png)

## Overview

This Snakemake pipeline handles the complete sequencing data processing workflow:
1. **BCL Conversion** - DRAGEN BCL-to-FASTQ conversion with per-lane sample sheets
2. **File Renaming** - Systematic renaming based on lane, group, position, and barcode
3. **Quality Analysis** - FastP quality metrics for all samples
4. **Visualization** - Quality plots (mean Phred scores, base composition)
5. **Report Generation** - Comprehensive HTML reports grouped by Order ID with embedded plots and download instructions
6. **Read Count Compilation** - Lane-level read counts formatted as CSV, aggregated per library
7. **Email Notifications** - Automated email delivery of reports and read counts

## Installation

```bash
git clone https://github.com/uci-grthub/bcl_conversion.git
cd bcl_conversion
```

## Environment

Python and the bioinformatics CLIs are provisioned with [pixi](https://pixi.sh) from
`pixi.toml` (locked in `pixi.lock`). Install pixi once, then let it build the environment:

```bash
curl -fsSL https://pixi.sh/install.sh | bash   # one-time install
pixi install                                    # solve/create env from pixi.lock
```

Run any command inside the environment with `pixi run`, or use the predefined tasks:

```bash
pixi run init                # one-time per-run setup (project config + samplesheet)
pixi run dry-run             # preview what would run
pixi run all                 # full workflow (snakemake --cores 8)
pixi run convert output/lane1
pixi run publish NovaSeqx xR101   # mirror finished run to the share + resend emails
pixi run masking-sweep 39 22 17   # one deliverable set per alternative R2 masking
pixi run masking-sweep-report     # compare those variants against the baseline lane
```

> `pixi run` auto-loads secrets from the shared per-platform `../.env` (a local `./.env`
> overrides it) and forces `SNAKEMAKE_PROFILE=profiles/default` (see `[activation]` in
> `pixi.toml` and `scripts/load_dotenv.sh`). You do **not** copy a `.env`, pass
> `--profile`, or run `source .env` — every `pixi run snakemake ...` already has both.

pixi manages Python (pandas, openpyxl, numpy, matplotlib, pillow, pyyaml, reportlab),
Snakemake, and the bioconda CLIs (`fastqc`, `flexbar`, `seqtk`, `fqtk`). Two dependencies
remain **system-level** and are not installed by pixi:

- **DRAGEN** (`/opt/dragen/<ver>/bin/dragen`) — licensed, FPGA-tied; must be on `PATH`.
- An **optional custom `flexbar` build** referenced by `flexbar_bin` in the config. A
  bioconda `flexbar` is provided by pixi; point `flexbar_bin` at it to drop the custom build.

> The legacy `bcl_convert` mamba/conda environment is being retired in favor of pixi.

## Key Files

- **`Snakefile`** - Main workflow definition; imports rules from `src/workflow_defs.smk`
- **`snakemake_config.yaml`** - Base configuration (paths, threads, email settings)
- **`snakemake_config_project.yaml`** - Project-specific configuration (overrides base settings)
- **`metadata/*.xlsx`** - Excel metadata with Summary sheet and per-project sheets
- **`scripts/publish_run.sh`** - `pixi run publish`: mirror run to share, touch, resend emails
- **`scripts/sync_run.sh`** - `sync_run` rsync mirror function (sourced by `publish_run.sh`)
- **`src/RunInfo_nn.xml`** - Normalized run configuration (auto-generated)

## Platforms & Auto-Detection

This pipeline supports two Illumina platforms/configurations. The platform is
**auto-detected from the metadata workbook** at workflow start (no config flag needed):

| Aspect | MiSeq i100 | NovaSeqX |
|--------|-----------|----------|
| Detection | Has a `Barcode Entries` sheet, no `Summary` sheet | Has a `Summary` sheet |
| Lanes | Single lane (`lane1`) | Up to 8 lanes (`lane1`…`lane8`) |
| Groups | Single group per lane | Multiple groups per lane |
| Order IDs | Inferred from `Lab ID` column of the first sheet | Read from the `Summary` sheet |
| Example `data_dir` | `/staging/nextcloud/Miseqi100/<run>` | `/staging/nextcloud/NovaseqX/<run>` |

The workflow prints `Detected MiSeq metadata format` (or proceeds with the NovaSeqX
Summary-sheet path) so you can confirm which mode is active. The run identifier below
(`{RUN}`, e.g. `iR011` / `xR077`) comes from your metadata filename.

## Configuration

Edit `snakemake_config_project.yaml` (project overrides layered over `snakemake_config.yaml`).

Most fields are prefilled by `pixi run init`; set `email_*` to **your** address.

**MiSeq i100 example**:

```yaml
library_name: "iR011"                    # Run identifier
metadata: "metadata/06262026_BXA66618-2426_iR011.xlsx"
data_dir: "/staging/nextcloud/Miseqi100/20260626_SH00564_0020_ASC2231455-SC3"
lanes: [1,2,3,4,5,6,7,8]                 # Superset; only lane1 is used for MiSeq
email_sender: "you@uci.edu"
email_recipient: "you@uci.edu"
```

**NovaSeqX example**:

```yaml
library_name: "xR077"                    # Run identifier
metadata: "metadata/251219_23G5F2LT3_10B_PE151_xR077.xlsx"
data_dir: "/staging/nextcloud/NovaseqX/20260115_LH00626_0088_A233NM2LT4"
lanes: [1,2,3,4,5,6,7,8]                 # Lanes to process (auto-detected from BaseCalls)
email_sender: "you@uci.edu"
email_recipient: "you@uci.edu"
```

## Metadata Format

### NovaSeqX (Summary-sheet format)
- **Summary sheet** (header at row 3):
  - `Lane`, `Gr` (Group), `Project Name`, `Masking`, `Fastq Link`
- **Per-project sheets** with sample details:
  - `Lane`, `Group`, `Sample Name`, `i7 Barcode Sequence`, `i5 Barcode Sequence`

**Masking format**: `R1:151, I1:8, I2:8, R2:151` → generates OverrideCycles

### MiSeq i100 (simple format)
- A **`Barcode Entries`** sheet with per-sample barcodes (no `Summary` sheet)
- The first sheet's **`Lab ID`** column supplies both project labels (e.g. `PaegB`)
  and Order IDs (e.g. `0626I-08`); order IDs match the pattern `\d+I-\d+`
- All samples are assigned to a single lane (`lane1`) and single group

## Workflow Steps

Configs are identified per lane as `lane{N}` (e.g. `lane1`). MiSeq i100 runs use only
`lane1`; NovaSeqX runs may use `lane1` through `lane8`. Generated sample sheets, renaming
maps, and per-lane artifacts live under `results/lane{N}/`.

### 1. Sample Sheet Generation (automatic)
- Parses metadata Excel file
- Generates per-lane sample sheets in `results/lane{N}/SampleSheet_lane{N}.csv`
- Creates renaming maps in `results/lane{N}/renaming_map_lane{N}.csv`
- Produces Flexbar barcode files for Flexbar-tagged projects

### 2. BCL Conversion
```bash
snakemake --cores 8 output/lane1
```
- Runs DRAGEN BCL Convert per lane configuration
- Applies OverrideCycles from metadata masking field
- Creates project subdirectories
- Renames FASTQ files using renaming map: `{Run}-L{Lane}-G{Group}-P{Position}-{Barcode}`

### 3. Quality Analysis (FastP)
```bash
snakemake --cores 4 results/fastp_lane1.done
```
- Runs FastP on all samples per config
- Outputs JSON stats to `results/fastp/lane{N}/{project}/{sample}.json`

### 4. Quality Plots
```bash
snakemake --cores 4 results/lane1/fastp_plots_lane1.done
```
- Generates mean Phred and base composition plots
- Outputs PNG files to `results/fastp_plots/lane{N}/{project}/{sample}-*.png`

### 5. Project/Order Reports
```bash
snakemake --cores 1 Reports/order_0626I-08/index.html
```
- Creates comprehensive HTML reports grouped by `Order ID`
- Includes summary of all projects associated with the order
- Embeds quality plots as base64 images
- Includes download instructions (browser, wget, HPC) and sorted md5 checksums
- Outputs:
  - `Reports/order_{id}/index.html`
  - `Reports/order_{id}/md5sums.txt`
  - `Reports/order_{id}/Download_Instructions.pdf`
  - `Reports/{project}/lane{lane}/index.html`

### 6. Read Count Compilation
```bash
snakemake --cores 1 results/iR011-count.csv
```
- Aggregates read counts across all lanes
- Formats as CSV with one `lane/group/sample/counts/index_rc` column block per lane-group
- Samples keep their metadata order within each block
- `index_rc` flags the submitted index(es) that had to be reverse-complemented to match
  the index reads (`i7`, `i5`, `i7+i5`); blank means delivered on the barcodes as submitted

### 7. Email Delivery
```bash
snakemake --cores 1 Reports/iR011_read_counts_email.done
```
- Sends the read count CSV and `Reports/rc_orientation_summary.csv` as attachments
- Uses SMTP (Gmail SSL, `smtp.gmail.com:465`, `GMAIL_APP_PASSWORD` from the environment)
- `SEND_EMAIL_DRY_RUN=1` composes the message without sending it

## Publishing a Finished Run

Once `pixi run all` has completed, publish the run with:

```bash
pixi run publish <instrument> <run_id>        # e.g. pixi run publish NovaSeqx xR101
```

`scripts/publish_run.sh` runs three steps in order:

1. `sync_run <instrument> <run_id> [dest_base] [parallel]` — rsync-mirrors the run
   directory to the share (default `dest_base`:
   `/mnt/jbod_localdisk/nextshare/bcl_convert/<instrument>/<run_id>`).
2. `snakemake --touch all` — rsync bumps mtimes, so outputs are re-marked current.
3. `snakemake --forcerun send_order_email` — re-sends the per-order download emails,
   now that the data is actually reachable on the share.

Extra arguments pass straight through to `sync_run`:

```bash
PARALLEL=4 pixi run publish NovaSeqx xR101                  # 4 parallel rsync jobs (default 2)
pixi run publish NovaSeqx xR101 /mnt/usb false              # custom dest, parallel off
```

Set the 4th argument to `false` for USB/local-disk destinations — there is no network
latency to hide and concurrent writes to one drive only cause seek contention.

Notes:

- Run it **from the run directory**, so the `snakemake` steps see the right config.
- `sync_run` is a shell function defined in `scripts/sync_run.sh` (in-repo, no dotfile
  setup needed); `publish_run.sh` sources it. It can also be called standalone:
  `bash scripts/sync_run.sh NovaSeqx xR101`.
- `sync_run` rewrites `nextcloud_dir_name`/`nextcloud_dir_path` in the **mirrored** copy
  of `snakemake_config_project.yaml` so links point at the JBOD share, and excludes
  `.snakemake`, `Reports`, and link logs from the transfer.
- Instrument/run casing is resolved case-insensitively (`NovaSeqx` matches `NovaSeqX`).

## Common Commands

**Dry run (see what would execute):**
```bash
snakemake -n
```

**Run entire workflow:**
```bash
snakemake --cores 8
```

**Run specific project report:**
```bash
snakemake --cores 4 Reports/MyProject/index.html
```

**Analyze undetermined indices:**
```bash
snakemake --cores 1 results/undetermined_indices/lane1.csv
```

**Force re-run a specific rule:**
```bash
snakemake --cores 4 -R compile_read_counts
```

**View rule graph:**
```bash
snakemake --rulegraph | dot -Tpdf > rulegraph.pdf
```

**View complete dependency graph:**
```bash
snakemake --dag | dot -Tpdf > dag.pdf
```

**Masking sweep for one lane/group** (after the main run finishes that lane — see
[Advanced Features](#advanced-features)):
```bash
pixi run masking-sweep              # default R2 lengths: 39, 22, 17
pixi run masking-sweep 39 22        # explicit list
SWEEP_LANE=8 SWEEP_GROUP=1 pixi run masking-sweep 39   # non-default lane/group
SWEEP_STOP_AFTER_SEED=1 pixi run masking-sweep 39      # build + seed, no pipeline run
```

**Compare sweep variants against the baseline:**
```bash
pixi run masking-sweep-report
SWEEP_FULL=1 pixi run masking-sweep-report   # prefix-check whole files, not first 1M reads
```

## Output Structure

```
output/
  lane{N}/
    {project}/
      {Run}-L{Lane}-G{Group}-P{Position}-{Barcode}-R1.fastq.gz
      {Run}-L{Lane}-G{Group}-P{Position}-{Barcode}-R2.fastq.gz

results/
  lane{N}/
    SampleSheet_lane{N}.csv
    renaming_map_lane{N}.csv
  fastp/
    lane{N}/{project}/{sample}.json
  fastp_plots/
    lane{N}/{project}/{sample}-mean_phred.png
    lane{N}/{project}/{sample}-base_comp.png
  undetermined_indices/
    lane{N}.csv
  {library}-count.csv

Reports/
  order_{id}/
    index.html
    md5sums.txt
    Download_Instructions.pdf
    email_sent.done
  {project}/
    lane{lane}/
      index.html
      md5sums.txt
  {library}_read_counts_email.done
```

## Undetermined Reads

Two config options control how Undetermined (unassigned) reads are handled per lane:

- **`keep_undetermined_configs`** - lanes whose Undetermined FASTQs are retained
  instead of deleted after conversion. Example: `keep_undetermined_configs: ['lane1']`
- **`report_undetermined_configs`** - lanes where Undetermined reads are treated as a
  normal sample: renamed into the lane's first project directory and flowed through the
  full pipeline (fastp QC, read counts, md5sums, nextcloud links, and the per-order HTML
  report). Lanes listed here are automatically added to `keep_undetermined_configs`.
  Example: `report_undetermined_configs: ['lane1']`

Undetermined reads are also kept automatically when a
`flexbar_barcodes_{config_id}.txt` file exists for the lane.

## Email Configuration

The workflow uses `src/send_email.py` with support for:
- Plain text or HTML content
- File attachments
- Configurable SMTP settings (default: smtp.uci.edu:25)

For OAuth2 (Gmail):
- Set up Google Cloud OAuth2 credentials
- Store `client_secret.json` and `token.json` in workspace
- Modify `send_email.py` to use `google-auth` libraries
- Set environment variables for credential paths

## Troubleshooting

**Missing lanes in workflow:**
- Check `detected_lanes` output at workflow start
- Verify `data_dir` in config points to the correct run directory (with `Data/Intensities/BaseCalls`)

**BCL conversion fails:**
- Verify `data_dir` and `run_info_path` are correct
- Check DRAGEN is available: `which dragen`
- Review OverrideCycles match actual run cycles

**No samples in report:**
- Check metadata Excel file has correct sheet names and headers
- Verify projects are listed in Summary sheet
- Look for "PROJECTS found in SampleSheet" in workflow output

**md5 mismatches:**
- Re-run specific project: `snakemake -R report_project --cores 1 Reports/{project}/md5sums.txt`
- Verify FASTQ files weren't modified after generation

## Advanced Features

**Flexbar / inline demultiplexing** (for Flexbar-tagged projects):
- Requires barcode FASTA files (auto-generated from metadata)
- `flexbar_barcode_leader_n` sets leading bases (e.g. a UMI) before the inline barcode
  in R1 (0 = barcode at position 1; 5 for PAREseq-style U5I6 libraries)
- `flexbar_retry_min_reads` triggers a reverse-complement retry pass if no sample
  exceeds the threshold after the forward pass
- Processes undetermined reads

**Excluding orders:**
- Set `exclude_order_ids: ["0626I-08"]` to skip processing, reports, and emails for
  specific Order IDs

**Scratch space for conversion:**
- Set `scratch_dir` to fast local NVMe; DRAGEN writes FASTQs there first, then moves
  them to `output/` (avoids writing directly to slow JBOD/network storage)

**Tile-specific processing:**
- Set `tiles: "1_1101"` in config for subset processing
- Useful for test runs or debugging

**Masking sweep** (`pixi run masking-sweep`):

Delivers one complete output set per alternative masking of a single lane/group —
QC, plots, md5s, links and an order report each — without re-running DRAGEN per
variant. Run it *after* the main run has finished the lane.

```bash
pixi run masking-sweep            # default variants: R2 39, 22, 17
pixi run masking-sweep 39 22      # explicit R2 lengths
pixi run masking-sweep-report     # compare variants against the baseline
```

- Only valid when the variants differ in the **R2 `Y` length alone** (same R1/I1/I2,
  same indexes). Then the shorter-R2 FASTQ is an exact prefix of the long-R2 FASTQ,
  so `seqtk trimfq -L` reproduces what DRAGEN would have written. A variant that
  changes an index length or R1 needs a real conversion instead.
- Each variant runs the unmodified pipeline in `sweeps/{library}_L{lane}_R2-{n}/`
  via `snakemake -d`; the Snakefile is untouched.
- Delivery folders stay distinct because the variant workbook's `Lab ID` gets an
  `_R2-{n}` suffix: `LinE_R2-39_0826I-53_xR112_L8_G1`.
- The `.output` and `.output_rc` trees are seeded from the main run and their
  `.done` files touched last, so neither `bcl_convert` nor `bcl_convert_rc`
  re-runs; the script aborts rather than letting DRAGEN start.
- Variant runs are addressed to the operator (`SWEEP_EMAIL`, default
  `kstachel@uci.edu`), never the customer. Restore `email_recipient` in that
  variant's `snakemake_config_project.yaml` before publishing one.
- Env knobs: `SWEEP_LANE`, `SWEEP_GROUP`, `SWEEP_CORES`, `SWEEP_EMAIL`,
  `SWEEP_FORCE`, `SWEEP_STOP_AFTER_SEED`.

## Notes

- Run commands via `pixi run` (environment provisioned from `pixi.toml` / `pixi.lock`)
- The workflow auto-detects lanes from the BaseCalls directory
- Sample sheets are generated once at workflow start from metadata
- md5 checksums are sorted by position number (P001, P002, ...)
- Reports include embedded images for email compatibility
- 2-week data retention policy is noted in all reports
