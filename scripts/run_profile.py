"""Fetch and render a company overview with one name/code argument."""
import json
import sys
import fetch_profile
from render_profile import render


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = fetch_profile.parser().parse_args(argv)
    status = fetch_profile.main(argv)
    if status or args.resolve_only:
        return status
    profile = json.loads((args.out / 'profile.json').read_text(encoding='utf-8'))
    output = args.out / 'company-profile.html'
    output.write_text(render(profile), encoding='utf-8')
    print(json.dumps({'html': str(output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
