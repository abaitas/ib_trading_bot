#!/bin/bash
# Run once on EC2: point 'ib' alias to repo's start_ib.sh.
# After deploy, 'ib' will use the script from ib_trading_bot/scripts/.

sed -i '/^alias ib=.*start_ib/d' ~/.bashrc 2>/dev/null || true
echo 'alias ib="/home/ubuntu/ib_trading_bot/scripts/start_ib.sh"' >> ~/.bashrc

echo "Done. Run: source ~/.bashrc   then type: ib"
echo "(Optional: rm ~/start_ib.sh to remove the old root copy)"
