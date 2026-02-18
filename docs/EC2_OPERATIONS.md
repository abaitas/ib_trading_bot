# EC2 Operations

## 1. Fix `ib` alias (use repo's start_ib.sh)

After deploy, run on EC2:

```bash
cd /home/ubuntu/ib_trading_bot
bash scripts/ec2-setup-ib-alias.sh
source ~/.bashrc
```

Then `ib` runs `/home/ubuntu/ib_trading_bot/scripts/start_ib.sh` (updated on each deploy).

Optional: remove old root copy to avoid confusion:
```bash
rm ~/start_ib.sh
```

---

## 2. Create an EC2 snapshot

**When:** Before major changes, or regularly for backup.

### Step 1: Open the EC2 console
1. AWS Console → EC2
2. Region: select your instance's region (e.g. us-east-1)

### Step 2: Find the root volume
1. Left sidebar → **Instances**
2. Select your instance
3. In the details pane below: **Storage** → click the root volume ID (e.g. `vol-xxxxx`)

Or: Left sidebar → **Elastic Block Store** → **Volumes** → find the volume attached to your instance (State: in-use)

### Step 3: Create snapshot
1. Select the volume
2. **Actions** → **Create snapshot**
3. **Description** (optional): e.g. `ib-trading-bot-backup-2026-02-18`
4. **Tags** (optional): Key `Name`, Value `ib-bot-backup`
5. **Create snapshot**

### Step 4: Wait
- Status: `pending` → `completed` (usually 2–10 minutes)
- EC2 → Snapshots → check progress

---

## 3. Delete unused volumes

**When:** After you've detached volumes and no longer need them.

### Step 1: List volumes
1. EC2 → **Volumes**
2. Filter or scan for **State**:
   - **available** = detached, can be deleted
   - **in-use** = attached to an instance (do not delete)

### Step 2: Confirm before delete
For each **available** volume, check:
- Is it from a snapshot you might need? (e.g. the one we attached to recover start_ib.sh)
- If unsure, leave it or add a tag like `keep` for review

### Step 3: Delete
1. Select the volume(s) to delete
2. **Actions** → **Delete volume**
3. Confirm

**Note:** Deleting a volume deletes its data. Snapshots are independent; deleting a volume does not delete snapshots created from it.
