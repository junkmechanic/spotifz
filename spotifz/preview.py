"""
Renders the fzf preview pane for the highlighted candidate line.

    <python> preview.py <track_dir> <track_id> <playlist_name> <added_at>

Executed as a script and never imported, which is why there is not a single
relative import below: importing the spotifz package reaches spotipy, and fzf
reruns this command on every cursor move, so that import would be paid on every
arrow key. Standard library only, one small file read.

The pane is for recall -- placing a track you do not recognise -- so it shows
what a person reads and none of the ids they cannot.
"""

import datetime
import json
import os
import sys

INDENT = '  '
LABEL_WIDTH = 12
# Under this the label column costs more room than it earns, so values stack.
NARROW_COLUMNS = 46
DEFAULT_COLUMNS = 80
ELLIPSIS = '…'

BOLD = '\033[1m'
DIM = '\033[2m'
RESET = '\033[0m'


def load_track(track_dir, track_id):
    """
    The only thing here that knows how tracks are stored. A missing or
    half-written file is a normal state -- the cache is rebuilt from scratch on
    every update -- so it reads as 'no track', not as an error.
    """
    try:
        with open(os.path.join(track_dir, track_id)) as ifile:
            return json.load(ifile)
    except (OSError, ValueError):
        return None


def styles(env):
    """
    fzf runs the preview with its output on a pipe, so isatty() is False even
    though the pane is plainly a terminal. NO_COLOR is the only signal worth
    reading here.
    """
    if env.get('NO_COLOR'):
        return (lambda text: text), (lambda text: text)
    return (
        lambda text: BOLD + text + RESET,
        lambda text: DIM + text + RESET,
    )


def columns(env):
    """fzf exports the pane's width, which is not the terminal's."""
    for name in ('FZF_PREVIEW_COLUMNS', 'COLUMNS'):
        try:
            value = int(env.get(name, ''))
        except ValueError:
            continue
        if value > 0:
            return value
    return DEFAULT_COLUMNS


def clean(value):
    """One row is one line: a name carrying a newline may not open another."""
    return ' '.join(str(value if value is not None else '').split())


def truncate(text, width):
    if width <= 0:
        return ''
    if len(text) <= width:
        return text
    if width == 1:
        return ELLIPSIS
    return text[: width - 1].rstrip() + ELLIPSIS


def artist_names(entity):
    return [
        clean(artist.get('name'))
        for artist in (entity or {}).get('artists') or []
        if clean(artist.get('name'))
    ]


def join_names(names, width):
    """
    Fits as many names as the pane holds and counts the rest, rather than
    cutting mid-name: '+3 more' still tells you it is a collaboration.
    """
    if not names:
        return ''
    joined = ', '.join(names)
    if len(joined) <= width:
        return joined
    for kept in range(len(names) - 1, 0, -1):
        candidate = '{}, +{} more'.format(', '.join(names[:kept]), len(names) - kept)
        if len(candidate) <= width:
            return candidate
    return truncate(names[0], width)


def format_duration(milliseconds):
    if not isinstance(milliseconds, int) or isinstance(milliseconds, bool):
        return ''
    if milliseconds < 0:
        return ''
    minutes, seconds = divmod(milliseconds // 1000, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return '{}:{:02d}:{:02d}'.format(hours, minutes, seconds)
    return '{}:{:02d}'.format(minutes, seconds)


def format_track_number(number, total):
    """
    'Track 11' is a number with no scale. With the album total it says where in
    the record you are, which is the whole reason the row is here.
    """
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        return ''
    if isinstance(total, int) and not isinstance(total, bool) and total >= number:
        return '{} of {}'.format(number, total)
    return str(number)


def release_year(release_date):
    """
    Spotify sends YYYY, YYYY-MM or YYYY-MM-DD depending on how much it knows.
    release_date_precision says which, and is not cached: the first four
    characters are the year in all three shapes.
    """
    year = str(release_date if release_date is not None else '')[:4]
    return year if len(year) == 4 and year.isdigit() else ''


def parse_added_at(value):
    text = clean(value)
    if not text:
        return None
    # Spotify stamps UTC with a trailing Z, which fromisoformat rejects until
    # 3.11 and the floor here is 3.9.
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def format_date(moment):
    # An unpadded day, which strftime cannot give portably: %-d is glibc, %#d
    # is Windows, and %d leaves '03 April'.
    return '{} {} {}'.format(moment.day, moment.strftime('%B'), moment.year)


def _plural(count, unit):
    return '{} {}{} ago'.format(count, unit, '' if count == 1 else 's')


def format_relative(moment, now):
    """
    The half of the date you actually read. Approximate on purpose: 'about a
    year' is what recall needs, and a precise interval would invite the
    verification this pane is not for.
    """
    days = (now - moment).days
    if days < 0:
        # A clock askew, or a cache from the future. Say nothing rather than
        # something wrong.
        return ''
    if days == 0:
        return 'today'
    if days == 1:
        return 'yesterday'
    if days < 7:
        return _plural(days, 'day')
    if days < 30:
        return _plural(days // 7, 'week')
    if days < 365:
        return _plural(days // 30, 'month')
    return _plural(days // 365, 'year')


def format_added(added_at, now):
    moment = parse_added_at(added_at)
    if moment is None:
        return ''
    relative = format_relative(moment, now)
    if not relative:
        return format_date(moment)
    return '{} · {}'.format(format_date(moment), relative)


def detail_rows(track, playlist_name, added_at, width, now):
    """
    The pane's two labelled groups: the recording, then the provenance. Rows
    whose value is empty are dropped by the caller rather than shown beside a
    label -- an old cache is missing several of these, and a labelled blank is
    how a pane looks broken.
    """
    album = track.get('album') or {}
    album_name = clean(album.get('name'))
    year = release_year(album.get('release_date'))
    if album_name and year:
        album_name = '{} ({})'.format(album_name, year)

    recording = [('Album', album_name)]
    # Only when it differs from the performer: that is the compilation and
    # soundtrack tell, and noise on every other track.
    album_artists = artist_names(album)
    if album_artists and album_artists != artist_names(track):
        recording.append(('Album by', join_names(album_artists, width)))
    recording.append(
        (
            'Track',
            format_track_number(track.get('track_number'), album.get('total_tracks')),
        )
    )
    recording.append(('Length', format_duration(track.get('duration_ms'))))

    provenance = [
        ('Playlist', clean(playlist_name)),
        ('Added', format_added(added_at, now)),
    ]
    return [recording, provenance]


def render(track, playlist_name, added_at, width, bold, dim, now):
    if track is None:
        return INDENT + dim('track not in cache')

    body = max(width - len(INDENT), 1)
    narrow = width < NARROW_COLUMNS
    value_width = body if narrow else max(body - LABEL_WIDTH, 1)

    # The two things you already know how to read come first and unlabelled.
    title = [bold(truncate(clean(track.get('name')) or 'unknown track', body))]
    performers = join_names(artist_names(track), body)
    if performers:
        title.append(dim(performers))

    groups = [title]
    for rows in detail_rows(track, playlist_name, added_at, value_width, now):
        lines = []
        for label, value in rows:
            if not value:
                continue
            value = truncate(value, value_width)
            # Stacked, the labels are what does not fit; the values still read
            # in order, which is the point of keeping the groups.
            lines.append(value if narrow else dim(label.ljust(LABEL_WIDTH)) + value)
        if lines:
            groups.append(lines)

    # One blank line between groups, no rules and no box: borders in a pane fzf
    # reflows are how a TUI starts looking cheap.
    return '\n\n'.join('\n'.join(INDENT + line for line in group) for group in groups)


def main(argv, env, now):
    track_dir, track_id, playlist_name, added_at = (list(argv) + ['', '', '', ''])[:4]
    bold, dim = styles(env)
    track = load_track(track_dir, track_id) if track_dir and track_id else None
    return render(track, playlist_name, added_at, columns(env), bold, dim, now)


if __name__ == '__main__':
    try:
        pane = main(
            sys.argv[1:], os.environ, datetime.datetime.now(datetime.timezone.utc)
        )
    except Exception:
        # A traceback in the pane is the one thing worse than a bad layout, and
        # there is nowhere for an error to go: fzf shows this and nothing else.
        pane = INDENT + 'preview unavailable'
    sys.stdout.write(pane + '\n')
