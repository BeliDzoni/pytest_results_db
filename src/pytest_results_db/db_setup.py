from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class TestCase(Base):
    __tablename__ = "test_cases"

    name = Column(String, nullable=False, primary_key=True, unique=True)
    markers = Column(String)
    description = Column(String)
    cls_name = Column(String)


class ExecutionTable(Base):
    __tablename__ = "execution_table"

    execution_id = Column(Integer, primary_key=True)
    test_name = Column(Integer, ForeignKey("test_cases.name"), nullable=False)
    params = Column(String)
    status = Column(String)
    expected = Column(String)
    result = Column(String)
    duration = Column(Float)
    timestamp = Column(DateTime, server_default=func.now())
    html = Column(String)
    text = Column(String)
    picture = Column(String)
    extras = Column(String)

    test_case = relationship("TestCase", backref="executions")
