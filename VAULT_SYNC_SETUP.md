# vault_sync.py Setup Guide

## Current Status

✅ **vault_sync.py** is built and tested locally.  
✅ **Weekly cron** (Sundays 3am) exports + syncs automatically.  
⏳ **Remote targets** pending: waiting for desktops to come online.

---

## Phase 1: Local Testing (TODAY ✓)

```bash
python vault_sync.py --targets /tmp/test-backup1 /tmp/test-backup2
```

Both desktops get a copy of `Memory-Export-YYYY-MM-DD.tar.gz` synced automatically.

---

## Phase 2: Remote Setup (WHEN DESKTOPS ARE ONLINE)

### Step 1: Set up SSH keys on each desktop

```bash
# On desktop1 and desktop2, create backup directory:
mkdir -p /media/backup/vault

# On main machine, generate SSH key (if you don't have one):
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""

# Copy public key to each desktop:
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@desktop1
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@desktop2
```

### Step 2: Test SSH access from main machine

```bash
ssh user@desktop1 "ls -la /media/backup/vault"
ssh user@desktop2 "ls -la /media/backup/vault"
```

Both should succeed without password prompts.

### Step 3: Update environment variable or cron target

**Option A: Environment variable (persistent)**
```bash
export VAULT_SYNC_TARGETS="user@desktop1:/media/backup/vault user@desktop2:/media/backup/vault"
python vault_sync.py
```

**Option B: Update cron (automatic)**
```bash
(crontab -l | grep -v "vault_export"; echo "0 3 * * 0 cd /home/thebackhand/Downloads/grok/Screenpipe-to-Obsidian && python3 vault_export.py && python3 vault_sync.py --targets user@desktop1:/media/backup/vault user@desktop2:/media/backup/vault >> /tmp/vault-backup.log 2>&1") | crontab -
```

### Step 4: Test the remote sync

```bash
python vault_sync.py --targets user@desktop1:/media/backup/vault user@desktop2:/media/backup/vault --dry-run
python vault_sync.py --targets user@desktop1:/media/backup/vault user@desktop2:/media/backup/vault
```

Verify files appear on both desktops:
```bash
ssh user@desktop1 "ls -lh /media/backup/vault/"
ssh user@desktop2 "ls -lh /media/backup/vault/"
```

---

## Weekly Backup Cycle

Every **Sunday at 3:00 AM**:
1. `vault_export.py` creates `Memory-Export-YYYY-MM-DD.tar.gz` in `~/Backups/Vault-Memory/`
2. `vault_sync.py` copies it to:
   - `/tmp/test-backup1/` (local test, for now)
   - `/tmp/test-backup2/` (local test, for now)
   - `user@desktop1:/media/backup/vault/` (when online)
   - `user@desktop2:/media/backup/vault/` (when online)

Check logs:
```bash
tail -f /tmp/vault-backup.log
```

---

## Disaster Recovery

If the main machine fails:

```bash
# On desktop1 or desktop2:
cd /media/backup/vault
tar -xzf Memory-Export-YYYY-MM-DD.tar.gz
# Now you have the entire Memory/ layer restored
```

---

## Notes

- Syncs use `rsync -av` (verbose, archive mode)
- Each desktop gets a **complete copy** (distributed redundancy)
- If one desktop fails, two others still have a backup
- SSH keys eliminate password prompts
- Cron logs to `/tmp/vault-backup.log`

Once the desktops are networked, update the targets and you're done.
