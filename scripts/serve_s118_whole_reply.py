"""Prepare or resume the fixed-material A trial; startup makes no model call."""
import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app/desktop"))

from whole_reply_trial import trial_server, APPLICATION_ID
from dynamic_subject_agent.first_life_development_trial import (DevelopmentReplyTrial,
    open_development_reply_trial, fixed_continuous_runs_root)
from dynamic_subject_agent.reply_protocol_trial import fixed_development_root
from dynamic_subject_agent.local_product import LocalProductConfig, open_first_life_development_trial
from dynamic_subject_agent.model_gateway import ModelGateway
from dynamic_subject_agent.frozen_attempt import canonical_json
from run_s112_reply_comparison import (SCENARIOS_PATH, prepare_branch,
    SeedAdapter, seed_branch, read_history)


ENTRY_VERSION = "s118-whole-reply-entry-1"
TITLES = {"objects-and-versions":"花瓶与书", "plan-versus-completion":"纸船与台灯"}


class TrialEntry:
    def __init__(self, entry_root: Path, *, live, transport=None):
        entry_root = entry_root.resolve()
        if (type(live) is not bool or live and entry_root != (fixed_development_root()/"whole-reply-entry").resolve()
            or not live and entry_root.is_relative_to(fixed_development_root().resolve())):
            raise ValueError("exact isolated trial entry directory required")
        self.entry_root, self.live, self.transport, self.products = entry_root, live, transport, {}
        pointer = entry_root / "current.json"
        if not entry_root.exists():
            entry_root.mkdir(parents=True, exist_ok=False)
            (entry_root / "initialized").mkdir(exist_ok=False)
            root = (fixed_continuous_runs_root() if live else entry_root/"runs") / str(uuid4())
            trial = open_development_reply_trial(root, SCENARIOS_PATH, live=live)
            branches = {}
            for scenario in trial.scenarios["scenarios"]:
                branch_id = scenario["id"] + "-A"
                branch = prepare_branch(root / branch_id, trial.scenarios)
                seed = SeedAdapter(trial.scenarios, scenario)
                with open_first_life_development_trial(branch.config, approval=trial, branch_id=branch_id,
                        definition_basis=branch.definition_basis, life_scope_digest=branch.life_scope_digest,
                        seed_gateway=ModelGateway(seed)) as product:
                    seed_branch(product, seed)
                branches[scenario["id"]] = dict(definition_basis=branch.definition_basis,
                    life_scope_digest=branch.life_scope_digest)
            value = dict(version=ENTRY_VERSION, live=live, root=str(root),
                manifest_digest=trial.manifest_digest, branches=branches)
            with pointer.open("x", encoding="utf-8") as output:
                output.write(canonical_json(value))
                output.flush()
                os.fsync(output.fileno())
        if not (entry_root / "initialized").is_dir() or not pointer.is_file():
            raise ValueError("trial initialization incomplete; existing data preserved")
        value = json.loads(pointer.read_text(encoding="utf-8"))
        if (set(value) != {"version","live","root","manifest_digest","branches"}
            or value["version"] != ENTRY_VERSION or value["live"] is not live
            or set(value["branches"]) != set(TITLES)):
            raise ValueError("trial entry pointer changed")
        root = Path(value["root"])
        expected_parent = fixed_continuous_runs_root() if live else entry_root/"runs"
        if not root.is_absolute() or root.parent.resolve() != expected_parent.resolve():
            raise ValueError("trial root changed")
        self.trial = DevelopmentReplyTrial(root, value["manifest_digest"])
        self.trial.read()
        self.branches = value["branches"]
        self.choices = {}
        try:
            for scenario in self.trial.scenarios["scenarios"]:
                case = scenario["id"]
                self.choices[case] = dict(title=TITLES[case], choices=[dict(id=str(i), text=row["user"])
                    for i,row in enumerate(scenario["turns"],1) if row["kind"] == "chat"])
                self.products[case] = self._open(case)
        except Exception:
            self.close()
            raise

    def _open(self, case):
        binding = self.branches[case]
        if set(binding) != {"definition_basis", "life_scope_digest"}:
            raise ValueError("trial branch pointer changed")
        root = self.trial.root / (case + "-A")
        return open_first_life_development_trial(LocalProductConfig(root/"DynamicSubjectAgent/m0/experiments", root/"state.json"),
            approval=self.trial, branch_id=case+"-A", definition_basis=binding["definition_basis"],
            life_scope_digest=binding["life_scope_digest"], _transport=self.transport)

    def reopen(self, case):
        if case not in self.products:
            raise ValueError("known trial case required")
        old = self.products[case]
        previous = read_history(old)
        identity = old.profile_id, old.timeline_id
        old.close()
        self.products.pop(case)
        product = self._open(case)
        if (product.profile_id, product.timeline_id) != identity or read_history(product) != previous:
            product.close()
            raise ValueError("trial cold recovery changed canonical history")
        self.products[case] = product
        return product

    def close(self):
        for product in self.products.values():
            product.close()
        self.products.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    from urllib.request import urlopen
    if args.port:
        try:
            with urlopen(f"http://127.0.0.1:{args.port}/health", timeout=1) as response:
                existing = json.loads(response.read(1024))
        except Exception:
            existing = None
        if existing == dict(application=APPLICATION_ID):
            print(f"小林试用已在运行：http://127.0.0.1:{args.port}", flush=True)
            if args.open_browser:
                import webbrowser
                webbrowser.open(f"http://127.0.0.1:{args.port}")
            return
    entry = None
    try:
        entry = TrialEntry(fixed_development_root()/"whole-reply-entry", live=True)
        server = trial_server(entry.products, choices=entry.choices, scope_key=entry.trial.manifest_digest,
            reopen=entry.reopen, port=args.port)
        print(f"小林试用已启动：http://127.0.0.1:{server.server_port}", flush=True)
        if args.open_browser:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{server.server_port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception:
        raise SystemExit("试用未能安全启动；现有聊天保留，请查看本地配置或记录完整性。") from None
    finally:
        if entry is not None:
            entry.close()


if __name__ == "__main__":
    main()
