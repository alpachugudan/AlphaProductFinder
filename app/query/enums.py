from __future__ import annotations

from enum import StrEnum


class Intent(StrEnum):
    LOOKUP_PRODUCT = "LOOKUP_PRODUCT"
    FILTER = "FILTER"
    FILTER_AND_RANK = "FILTER_AND_RANK"
    COMPARE_PRODUCTS = "COMPARE_PRODUCTS"
    CROSS_FAMILY_SEARCH = "CROSS_FAMILY_SEARCH"
    RELATION_SEARCH = "RELATION_SEARCH"
    AGGREGATE = "AGGREGATE"
    EXPLAIN_TERM = "EXPLAIN_TERM"
    UNSUPPORTED_PREDICTION = "UNSUPPORTED_PREDICTION"


class ProductFamily(StrEnum):
    BOND_KR = "BOND_KR"
    ETF_KR = "ETF_KR"
    ETF_GLOBAL = "ETF_GLOBAL"
    FUND_PUBLIC = "FUND_PUBLIC"


class Operator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    IN = "IN"
    CONTAINS = "CONTAINS"
    GTE = "GTE"
    LTE = "LTE"
    BETWEEN = "BETWEEN"
    IS_NULL = "IS_NULL"
    NOT_NULL = "NOT_NULL"


class Direction(StrEnum):
    ASC = "ASC"
    DESC = "DESC"


class AsOfRequirement(StrEnum):
    SHOW_FIELD_DATE = "SHOW_FIELD_DATE"


class MissingPolicy(StrEnum):
    EXCLUDE_AND_DISCLOSE = "EXCLUDE_AND_DISCLOSE"


class EntityType(StrEnum):
    PRODUCT = "PRODUCT"
    COMPANY = "COMPANY"
    INDEX = "INDEX"
    THEME = "THEME"
    SECTOR = "SECTOR"
    ISSUER = "ISSUER"
    MANAGER = "MANAGER"


class RelationType(StrEnum):
    HOLDS = "HOLDS"
    SUBSIDIARY_OF = "SUBSIDIARY_OF"
    AFFILIATE_OF = "AFFILIATE_OF"
    TRACKS_INDEX = "TRACKS_INDEX"
    BELONGS_TO_THEME = "BELONGS_TO_THEME"


class GroundingRule(StrEnum):
    SYNONYM = "SYNONYM"
    EXACT = "EXACT"
    REGISTRY_LABEL = "REGISTRY_LABEL"
