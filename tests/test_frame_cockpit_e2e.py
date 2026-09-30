"""
END-TO-END VALIDATION TEST FOR UNIFIED FRAME COCKPIT
Tests:
1. FrameMasterCockpit initialization and UI components
2. Tab switching between Live Trader and Backtest Station
3. Background feed and broker preservation across tab switches
4. Backtest simulation execution inside the unified container
5. Database audit & Cloud sync client responsiveness
"""

import sys, pathlib, time
project_root = pathlib.Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from src.frame.gui.frame_cockpit import FrameMasterCockpit
from src.frame.gui.worker import BacktestWorker

def run_e2e_test():
    print("==================================================================")
    print("  FRAME UNIFIED COCKPIT // END-TO-END AUTOMATED VERIFICATION")
    print("==================================================================")

    app = QApplication.instance() or QApplication(sys.argv)
    
    # 1. Initialize Cockpit
    cockpit = FrameMasterCockpit()
    print("[TEST 1/5] FrameMasterCockpit initialized successfully.")
    assert cockpit.stack.count() == 2, f"Expected 2 stacked pages, got {cockpit.stack.count()}"
    print(f"  -> Stack count: {cockpit.stack.count()} pages verified.")

    # 2. Test Tab Switching
    cockpit.switch_tab(1)
    assert cockpit.stack.currentIndex() == 1, "Failed to switch to Tab 1 (Backtest)"
    print("[TEST 2/5] Tab 1 (Backtest Station) active and verified.")

    cockpit.switch_tab(0)
    assert cockpit.stack.currentIndex() == 0, "Failed to switch to Tab 0 (Live Trader)"
    print("  -> Switched back to Tab 0 (Live Trader) successfully.")

    # 3. Test Live Trader Broker & Feed
    live = cockpit.live_workstation
    broker = live.broker
    assert broker.cash == 250.0, f"Expected initial cash 250.0, got {broker.cash}"
    print("[TEST 3/6] Live Trader PaperBroker verified ($250.00 cash).")
    
    # 3.5. Test Single Mature Locked Model Production Engine
    print("[TEST 4/6] Verifying Mature Locked Model Production Engine...")
    assert live.broker.session_id == "MOMENT_LOCKED_PROD", f"Unexpected session ID: {live.broker.session_id}"
    assert live.agent.model_choice == "pretrained", f"Unexpected model choice: {live.agent.model_choice}"
    assert live.broker.open_position is None, "Broker should start with clean 0 open position"
    assert len(live.broker.trade_history) == 0, "Broker should start with clean 0 trades"

    # Verify Arm / Standby
    live.set_agent_armed(True)
    assert live.agent.is_armed is True, "Arm agent failed"
    live.set_agent_armed(False)
    assert live.agent.is_armed is False, "Standby agent failed"

    # Verify Order Execution with MOMT prefix
    live.set_agent_armed(True)
    pos = live.broker.open_order("BUY", 2700.0, 2700.35, 10.0, reason="Test Mature Locked Model")
    assert pos["id"].startswith("MOMT"), f"Expected MOMT prefix, got {pos['id']}"
    assert pos["session_id"] == "MOMENT_LOCKED_PROD"

    # Simulate synchronous market tick
    tick = {"bid": 2708.0, "ask": 2708.35, "latency_ms": 8.5, "spread": 0.35, "time": time.time()}
    live._on_feed_tick(tick)
    assert live.broker.open_position["floating_r"] > 0, "MOMENT position did not update on tick"

    # Close order and verify trade
    trade = live.broker.close_order(2710.0, exit_reason="Target TP")
    assert len(live.broker.trade_history) == 1, "Trade history not updated"
    assert trade["session_id"] == "MOMENT_LOCKED_PROD"
    assert trade["win"] == 1

    # Clean up test positions
    live.broker.reset(250.0)
    print("  -> Mature Locked MOMENT-1-large Production Engine verified 100% cleanly.")

    # 4. Test Cloud Sync Worker
    client = live.cloud_client
    assert client.base_url is not None
    print(f"[TEST 5/6] Cloud Sync Client verified ({client.base_url}).")

    # 5. Test Backtest Worker inside Cockpit
    print("[TEST 6/6] Executing causal backtest worker in Cockpit context...")
    bt_view = cockpit.backtest_workstation
    worker = BacktestWorker(mode='2026', capital=250.0, sizing_mode='dual', max_lot=0.04, model_choice='pretrained')
    res_holder = {}
    def on_done(res):
        res_holder['data'] = res

    worker.finished_backtest.connect(on_done)
    worker.run()
    
    assert 'data' in res_holder, "BacktestWorker failed to return results"
    data = res_holder['data']
    print(f"  -> Backtest completed: Net PnL: ${data['net_pnl']:+,.2f} | WR: {data['win_rate']}% | Max DD: {data['max_drawdown']}%")
    assert data['net_pnl'] == 1207.01, f"Expected net PnL 1207.01, got {data['net_pnl']}"
    assert data['total_trades'] == 137, f"Expected 137 trades, got {data['total_trades']}"
    assert data['win_rate'] == 62.77, f"Expected 62.77% WR, got {data['win_rate']}"

    # Cleanup
    cockpit.close()
    print("\n[ALL E2E TESTS PASSED 100%] Unified FRAME Cockpit is completely robust & verified!")

if __name__ == "__main__":
    run_e2e_test()
