# Generate emails for expiring Globus Guest Collections

When you make a Globus Guest Collection, by default, it will continue to exist
forever.  That can lead to Guest Collections piling up.  Since each Guest
Collection takes up real resources on each DTN (configuration files, TLS
certificates, etc.), there is a small but real cost.

Since GCS 5.4.66, Globus has been tracking when each Collection was last
accessed.  Since GCS 5.4.82, Mapped Collections now have an
`auto_delete_timeout` property: Set to a non-zero number of days, Guest
Collections not used for that many days will be automatically deleted.  Setting
the `skip_auto_delete` property on a Guest Collection exempts it from deletion.

Globus notifies Guest Collection owners as deletion-day approaches, but when
the feature is first turned on, Guest Collections which are already due for
deletion get deleted without notification.

This script identifies which Guest Collections would be deleted
immediately, and drafts deletion-warning emails.  Actually sending the emails
is left as an exercise for the user.

# Requirements

Python 3.11 or later.

The packages [globus-sdk](https://pypi.org/project/globus-sdk/) and
[Jinja2](https://pypi.org/project/Jinja2/).  [Inline script
metadata](https://packaging.python.org/en/latest/specifications/inline-script-metadata/#inline-script-metadata)
is included in the script, so commands like [uv
run](https://docs.astral.sh/uv/reference/cli/#uv-run) may be used to run the
script.

A Globus Native App's Client ID.  The script includes a Native App Client ID,
but there is no guarantee that it will continue working.

Permission on the Endpoint or Collection that you plan on examining.  You need
at least Activity Monitor access.

# Execution

If you will provide your own Globus Native App Client ID, put it in the
`EEGC_CLIENT_ID` environment variable.

To run with `uv run`:

```
uv run email_expiring_guest_collections.py --cutoff-days 379 templates outputs ENDPOINT_UUID [COLLECTION_UUID]
```

`--cutoff-days` is the cutoff for generating emails.  Guest Collections
accessed more than this many days ago will have an email generated.  This is an
optional paramter: If you do not set it, the default is 379 (one year plus two
weeks).

`templates` is the path to the templates directory.  This is explained in a
following section.

`outputs` is the path to an empty directory.  Emails to send are written here.
This is explained in a following section.

`ENDPOINT_UUID` is the UUID of the Endpoint to examine.  This is required, even
if you only want to send emails for a single Mapped Collection.

`COLLECTION_UUID` is an optional UUID of a Collection.  If provided, this is
the only Collection that will be examined, and you only need a Role on this
Collection.  If you do not provide this, then all Collections on the Endpoint
will be examined, and you will need a Role on the Endpoint.

# Templates

The script uses [Jinja](https://jinja.palletsprojects.com/en/stable/) templates
to generate the subject line and body for each email.  When you run the script,
you provide the path to the templates directory.

Two templates are used:

* `subject.jinja2` generates the subject line.  This must generate a single
  line of output (it's OK if the last character of the output is a newline).

* `message.jinja2` generates the body of the message.  Since the script does
  not actually send any emails, the format of the template is up to you.  The
  example provided in the repo generates HTML suitable for use in FreshDesk.

When processed, each template is given four variables:

* **collection**, a Python dict: The output of a [Get information about a
  collection](https://docs.globus.org/globus-connect-server/v5.4/api/openapi_Collections/#getCollection)
  GCS API call.  The contents of the dict will correspond to one of the
  "Collection" documents from the [Schemas page](https://docs.globus.org/globus-connect-server/v5.4/api/openapi_schemas/).  

  To determine which schema version you should expect, check the [list of API
  changes](https://docs.globus.org/globus-connect-server/v5.4/api/#changes).
  For example, if you are running GCS 5.4.99, you should expect Collection
  schema version 1.15.0.

  This Collection document will not include any Private fields.  Also,
  Collections which have never been accessed will not have `last_access` set.

* **parent**, a Python dict: Like *collection*, but for the parent Mapped
  Collection.

* **earliest_last_access**, a Python
  [datetime.date](https://docs.python.org/3/library/datetime.html#datetime.date):
  This is the date when the Endpoint started tracking `last_access` on
  Collections.  It will either be the date the Endpoint was set up, or the date
  the Endpoint was upgraded GCS 5.4.66 (or later).

* **days_since_last_activity**, an integer: This is the number of days that
  have elapsed between now and the Collection's last access.  If a Collection
  has never been accessed, then it is the number of days between now and
  *earliest_last_access*.

# Outputs

When the program is run, the outputs directory must be empty.  Even a macOS
`.DS_Store` file will mean that it is not empty.

For every Guest Collection that needs an email sent, three files will be
written in the outputs directory.  The three files will share a common prefix:
The UUID of the Guest Collection.

The `outputs` directory in this repository includes example files for the fake
Guest Collection UUID `de43f268-d7e9-11f1-ae03-5ec87b775b0c`.

The three files are as follows:

* `UUID.message`: The body of the email that should be sent.  This is the
  output of rendering the `message.jinja2` template.  It does not use a `.txt`
  extension, because it might not be text (it might be HTML, or something
  else).  It is, however, UTF-8 encoded.

* `UUID-subject.txt`: The subject line to use for the email.  This is the
  output of rendering the `subject.jinja2` template.  It is also UTF-8 encoded.

* `UUID-recipients.txt`: The recipients to use for the email.  This file is
  ASCII-encoded.  It will have zero, one, or two lines.

  If the Guest Collection owner has an email address available, that will be
  included in the file first.  Some active Globus Identities—primarily service
  accounts—do not have an email address.  If the owner has no email address
  available, the program will print a warning, but it will continue running.

  If the Guest Collection record has a contact email, that will be included in
  the file next.

For example purposes, the `outputs` directory in this repository also includes
a PNG image, showing what the example `message.jinja2` template—written in
FreshDesk HTML—looks like when sent through to an email client.

# Copyright & Contributions

Written by [A. Karl Kornel](akkornel@stanford.edu) in November 2026.

© The Board of Trustees of the Leland Stanford Junior University

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

This project has a limited lifetime.  It is likely that the repository will be
archived not long after publication, so contributions might not be accepted.
If you change it, you should consider forking the repository and publishing
your changes!
