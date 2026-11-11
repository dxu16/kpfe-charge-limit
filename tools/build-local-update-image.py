"""Build the local install image with the same-base update check."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


UPDATER = 'usr/libexec/armada/armada-update'
RECORD = '/usr/share/armada/kpfe-charge-limit-build.json'
PATCH = (Path(__file__).resolve().parents[1] /
         'experimental/local-image-update/suppress-recorded-base-update.patch')


def read_image_file(image, command):
    return subprocess.check_output([
        'podman', 'run', '--rm', '--pull=never', '--network=none',
        '--entrypoint', '/usr/bin/sh', image, '-ec', command,
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-image', required=True)
    parser.add_argument('--output-image', required=True)
    parser.add_argument('--base-ref', help='Official channel used to build the input image')
    parser.add_argument('--base-digest', help='Official registry manifest digest for that build')
    args = parser.parse_args()
    for image in (args.input_image, args.output_image):
        if not re.fullmatch(r'localhost/[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*', image):
            parser.error('Use tagged localhost image references')
    if bool(args.base_ref) != bool(args.base_digest):
        parser.error('Provide both base fields or use the record in the input image')
    status = subprocess.run(['podman', 'image', 'exists', args.output_image]).returncode
    if status == 0:
        parser.error('Output tag already exists. Use a new tag for this build.')
    if status != 1:
        raise SystemExit(f'Could not check the output tag. Podman exited {status}.')

    raw = read_image_file(args.input_image, f'if test -e {RECORD}; then cat {RECORD}; fi')
    record = json.loads(raw) if raw else {}
    if not isinstance(record, dict):
        parser.error('Invalid build record in input image')
    for field, supplied, pattern in (
        ('base_image_ref', args.base_ref, r'ghcr\.io/armada-os/armada:(stable|beta|preview)'),
        ('base_image_digest', args.base_digest, r'sha256:[0-9a-f]{64}'),
    ):
        value = supplied or record.get(field, '')
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            parser.error(f'Missing or invalid {field}')
        if field in record and record[field] != value:
            parser.error(f'{field} differs from the input image record')
        record[field] = value

    updater = read_image_file(args.input_image, f'cat /{UPDATER}')
    original_hash = hashlib.sha256(updater).hexdigest()
    with tempfile.TemporaryDirectory(prefix='kpfe-updater-image-') as directory:
        context = Path(directory)
        path = context / UPDATER
        path.parent.mkdir(parents=True)
        path.write_bytes(updater)
        apply = ['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'apply']
        try:
            subprocess.run([*apply, '--check', str(PATCH)], cwd=context, check=True)
        except subprocess.CalledProcessError:
            raise SystemExit('Armada updater has changed. Rebase and retest the updater patch before building.')
        subprocess.run([*apply, str(PATCH)], cwd=context, check=True)
        (context / 'build-record.json').write_text(json.dumps(record, indent=2) + '\n')
        (context / 'Containerfile').write_text(f'''FROM {args.input_image}
RUN test "$(sha256sum /{UPDATER} | cut -d' ' -f1)" = "{original_hash}"
COPY --chmod=0755 {UPDATER} /{UPDATER}
COPY build-record.json {RECORD}
RUN bash -n /{UPDATER} && bootc container lint
''')
        subprocess.run(['podman', 'build', '--pull=never', '--network=none',
                        '-t', args.output_image, str(context)], check=True)


if __name__ == '__main__':
    main()
