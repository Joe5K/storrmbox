from sqlalchemy.orm import relationship
from datetime import timedelta, datetime

from .extensions import db


def time_now():
    return datetime.utcnow().replace(microsecond=0)


def time_future(delta_hours=12, current_time=time_now()):
    return current_time + timedelta(hours=delta_hours)


def time_past(delta_hours=12, current_time=time_now()):
    return current_time - timedelta(hours=delta_hours)


class CRUDMixin(object):
    """Mixin that adds convenience methods for CRUD (create, read, update, delete)
    operations.
    """

    @classmethod
    def create(cls, **kwargs):
        """Create a new record and save it the database."""
        instance = cls(**kwargs)
        return instance.save()

    def update(self, commit=True, **kwargs):
        """Update specific fields of a record."""
        # Prevent changing ID of object
        kwargs.pop('id', None)
        for attr, value in kwargs.items():
            # Flask-RESTful makes everything None by default :/
            if value is not None:
                setattr(self, attr, value)
        return commit and self.save() or self

    def save(self, commit=True):
        """Save the record."""
        db.session.add(self)
        if commit:
            db.session.commit()
        return self

    def delete(self, commit=True):
        """Remove the record from the database."""
        db.session.delete(self)
        return commit and db.session.commit()


class Model(CRUDMixin, db.Model):
    """Base model class that includes CRUD convenience methods."""
    __abstract__ = True


# From Mike Bayer's "Building the app" talk
# https://speakerdeck.com/zzzeek/building-the-app
class SurrogatePK(object):
    """A mixin that adds a surrogate integer 'primary key' column named
    ``id`` to any declarative-mapped class.
    """
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)

    @classmethod
    def get_by_id(cls, id):
        if id <= 0:
            raise ValueError('ID must not be negative or zero!')
        if (isinstance(id, (bytes, str)) and id.isdigit()) or isinstance(id, (int, float)):
            return cls.query.get(int(id))
        return None


def ReferenceCol(tablename, nullable=False, pk_name='id', **kwargs):
    """Column that adds primary key foreign key reference.
    Usage: ::
        category_id = ReferenceCol('category')
        category = relationship('Category', backref='categories')
    """
    return db.Column(db.ForeignKey("{0}.{1}".format(tablename, pk_name)),
        nullable=nullable, index=True, **kwargs)  # pragma: no cover
