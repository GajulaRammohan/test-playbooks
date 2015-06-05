import os
import hashlib
import time
import tempfile
import json
from datetime import datetime, timedelta

LICENSES = {
    'basic': {
        'features': {
            'activity_streams': False,
            'ha': False,
            'ldap': False,
            'multiple_organizations': False,
            'surveys': False,
            'system_tracking': False,
        },
        'license_name': 'Basic',
    },
    'enterprise': {
        'features': {
            'activity_streams': True,
            'ha': True,
            'ldap': True,
            'multiple_organizations': True,
            'surveys': True,
            'system_tracking': True,
        },
        'license_name': 'Enterprise',
    },
    'legacy': {
        'features': {
            'activity_streams': True,
            'ha': True,
            'ldap': True,
            'multiple_organizations': True,
            'surveys': True,
            'system_tracking': False,
        },
        'license_name': 'Legacy',
    },
}


def generate_license_file(**kwargs):
    meta = generate_license(**kwargs)

    (fd, fname) = tempfile.mkstemp(suffix='.json')
    os.write(fd, json.dumps(meta))
    os.close(fd)

    return fname


def generate_aws_file(**kwargs):
    meta = generate_aws(**kwargs)

    (fd, fname) = tempfile.mkstemp(suffix='.json')
    os.write(fd, json.dumps(meta))
    os.close(fd)

    return fname


def generate_license(instance_count=20, contact_email="art@vandelay.com",
                     company_name="Vandelay Industries", contact_name="Art Vandelay",
                     license_date=None, days=None, trial=None, eula_accepted=True,
                     license_type='legacy', features={}):

    def to_seconds(itime):
        '''
        Convenience method to convert a time into seconds
        '''
        return int(float(time.mktime(itime.timetuple())))

    # TODO: default to random UTF-8 fields for company_name, company_email and
    # contact_email
    # Generate license key (see ansible-commander/private/license_writer.py)
    meta = dict(instance_count=instance_count,
                contact_email=contact_email,
                company_name=company_name,
                contact_name=contact_name,
                license_type=license_type,
                features=features)

    # Be sure to accept the eula
    meta['eula_accepted'] = eula_accepted

    # Only generate a trial license if requested
    if isinstance(trial, bool):
        meta['trial'] = trial

    # Determine license_date
    if days is not None:
        meta['license_date'] = to_seconds(datetime.now() + timedelta(days=days))
    elif license_date is not None:
        meta['license_date'] = license_date

    sha = hashlib.sha256()
    sha.update("ansibleworks.license.000")
    sha.update(meta['company_name'].encode('utf-8'))
    sha.update(str(meta['instance_count']))
    sha.update(str(meta['license_date']))

    # Set license type
    if license_type != 'legacy':
        sha.update('{license_type:%s}' % license_type)

    # Only generate a trial license if requested
    if meta.get('trial', False):
        sha.update(str(meta['trial']))

    # Append features
    default_features = LICENSES[license_type]['features']
    for feature in sorted(default_features.keys()):
        if feature not in features:
            continue
        if features[feature] == default_features[feature]:
            continue
        feature_str = '{%s:%r}' % (feature, features[feature])
        sha.update(feature_str)

    meta['license_key'] = sha.hexdigest()
    return meta


def generate_aws(instance_count=30, ami_id="ami-eb81b182",
                 instance_id="i-fd64c1d3", license_type='legacy'):
    # Generate license key (see ansible-commander/private/license_writer.py)
    meta = dict(instance_count=instance_count)

    sha = hashlib.sha256()
    sha.update("ansibleworks.license.000")
    sha.update(str(meta['instance_count']))
    sha.update(str(ami_id))
    sha.update(str(instance_id))

    # Set license type
    if license_type != 'legacy':
        sha.update('{license_type:%s}' % license_type)

    meta['license_key'] = sha.hexdigest()

    return meta
