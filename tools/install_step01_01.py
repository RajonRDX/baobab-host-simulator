#!/usr/bin/env python3
"""
INSTALLER: tools/install_step01_01.py
STEP 1 — Bank, Processing System & BIN Management — Script 1 of 3
Adds ORM models, Pydantic v2 schemas, and idempotent ITCL-first seeding for:
  - processing_systems (ITCL, VISA, MASTERCARD, NPSB, INTERNAL)
  - institutions (xBank, yBank, zBank -> all under ITCL)
  - institution_processing_systems (multi-network participation junction)
  - bin_ranges (synthetic BIN ranges mapped to xBank, yBank, zBank under ITCL)
"""

from pathlib import Path
import sys

BASE_DIR = Path(r"E:\HOST_VSCODE\host-simulator").resolve()
sys.path.insert(0, str(BASE_DIR))

from tools.patcher import PatcherSession, parse_installer_args

MODELS_ADDITION = '''

# ==============================================================================
# F. PROCESSING SYSTEMS, INSTITUTIONS (BANKS) & BIN RANGES (STEP 1)
# ==============================================================================

class ProcessingSystem(Base):
    __tablename__ = "processing_systems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    ps_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)  # ITCL, VISA, MASTERCARD, NPSB, INTERNAL
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    system_type: Mapped[str] = mapped_column(String(40), nullable=False, default="HOST_SWITCH")  # HOST_SWITCH, CARD_SCHEME, NATIONAL_SWITCH, INTERNAL
    message_format: Mapped[str] = mapped_column(String(40), nullable=False, default="TIC_V2164E")  # TIC_V2164E, ISO8583_1987
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    institutions: Mapped[List["Institution"]] = relationship(
        "Institution", back_populates="primary_processing_system"
    )
    institution_links: Mapped[List["InstitutionProcessingSystem"]] = relationship(
        "InstitutionProcessingSystem", back_populates="processing_system", cascade="all, delete-orphan"
    )
    bin_ranges: Mapped[List["BinRange"]] = relationship(
        "BinRange", back_populates="processing_system"
    )


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    institution_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)  # XBANK, YBANK, ZBANK, IFIC
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    short_name: Mapped[Optional[str]] = mapped_column(String(60))
    acquirer_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # DE32 Acquiring Institution ID
    forwarding_id: Mapped[Optional[str]] = mapped_column(String(20))  # DE33 Forwarding Institution ID
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="BOTH")  # ISSUER, ACQUIRER, BOTH
    processing_system_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_systems.id"), nullable=False, index=True
    )
    country_code: Mapped[str] = mapped_column(String(3), nullable=False, default="050")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    settlement_account_number: Mapped[Optional[str]] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    primary_processing_system: Mapped["ProcessingSystem"] = relationship(
        "ProcessingSystem", back_populates="institutions"
    )
    processing_system_links: Mapped[List["InstitutionProcessingSystem"]] = relationship(
        "InstitutionProcessingSystem", back_populates="institution", cascade="all, delete-orphan"
    )
    bin_ranges: Mapped[List["BinRange"]] = relationship(
        "BinRange", back_populates="institution", cascade="all, delete-orphan"
    )


class InstitutionProcessingSystem(Base):
    """
    Many-to-many participation table allowing an ITCL bank to also participate in
    VISA, MASTERCARD, NPSB, or future processing systems with scheme-specific IDs.
    """
    __tablename__ = "institution_processing_systems"
    __table_args__ = (
        UniqueConstraint("institution_id", "processing_system_id", name="uq_inst_proc_system"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    processing_system_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[str] = mapped_column(String(40), nullable=False)
    acquirer_id: Mapped[Optional[str]] = mapped_column(String(30))
    network_identifier: Mapped[Optional[str]] = mapped_column(String(30))
    issuer_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    acquirer_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    message_format: Mapped[str] = mapped_column(String(40), nullable=False, default="TIC_V2164E")
    routing_configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    institution: Mapped["Institution"] = relationship("Institution", back_populates="processing_system_links")
    processing_system: Mapped["ProcessingSystem"] = relationship("ProcessingSystem", back_populates="institution_links")


class BinRange(Base):
    __tablename__ = "bin_ranges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    bin_prefix: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    bin_low: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    bin_high: Mapped[str] = mapped_column(String(19), nullable=False, index=True)
    pan_length: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=16)
    institution_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    processing_system_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("processing_systems.id"), nullable=False, index=True
    )
    card_type: Mapped[str] = mapped_column(String(30), nullable=False, default="DEBIT")  # DEBIT, CREDIT, PREPAID
    card_product: Mapped[str] = mapped_column(String(60), nullable=False, default="VISA_DEBIT_CLASSIC")
    scheme: Mapped[str] = mapped_column(String(30), nullable=False, default="ITCL")
    country_code: Mapped[str] = mapped_column(String(3), nullable=False, default="050")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BDT")
    is_on_us: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    institution: Mapped["Institution"] = relationship("Institution", back_populates="bin_ranges")
    processing_system: Mapped["ProcessingSystem"] = relationship("ProcessingSystem", back_populates="bin_ranges")
'''

SCHEMAS_ADDITION = '''

# ==============================================================================
# STEP 1 SCHEMAS: PROCESSING SYSTEMS, INSTITUTIONS & BIN RANGES
# ==============================================================================

class ProcessingSystemCreate(BaseModel):
    ps_code: str = Field(..., description="Unique processing system code, e.g. ITCL, VISA, MASTERCARD, NPSB")
    name: str
    system_type: str = "HOST_SWITCH"
    message_format: str = "TIC_V2164E"
    enabled: bool = True
    is_default: bool = False
    configuration: Dict[str, Any] = Field(default_factory=dict)


class ProcessingSystemUpdate(BaseModel):
    name: Optional[str] = None
    system_type: Optional[str] = None
    message_format: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    configuration: Optional[Dict[str, Any]] = None


class ProcessingSystemOut(ProcessingSystemCreate):
    id: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InstitutionCreate(BaseModel):
    institution_code: str = Field(..., description="Unique bank code, e.g. XBANK, YBANK, ZBANK, IFIC")
    name: str
    short_name: Optional[str] = None
    acquirer_id: str = Field(..., description="DE32 Acquiring Institution Identification Code")
    forwarding_id: Optional[str] = None
    role: str = "BOTH"  # ISSUER, ACQUIRER, BOTH
    processing_system_id: Optional[str] = Field(
        None,
        description="Primary processing system ID. Defaults to ITCL if omitted.",
    )
    ps_code: Optional[str] = Field(
        "ITCL",
        description="Fallback processing system code if processing_system_id is not supplied (defaults to ITCL).",
    )
    country_code: str = "050"
    currency: str = "BDT"
    settlement_account_number: Optional[str] = None
    status: str = "ACTIVE"
    configuration: Dict[str, Any] = Field(default_factory=dict)


class InstitutionUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    acquirer_id: Optional[str] = None
    forwarding_id: Optional[str] = None
    role: Optional[str] = None
    processing_system_id: Optional[str] = None
    country_code: Optional[str] = None
    currency: Optional[str] = None
    settlement_account_number: Optional[str] = None
    status: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None


class InstitutionOut(BaseModel):
    id: str
    institution_code: str
    name: str
    short_name: Optional[str] = None
    acquirer_id: str
    forwarding_id: Optional[str] = None
    role: str
    processing_system_id: str
    ps_code: Optional[str] = None
    ps_name: Optional[str] = None
    country_code: str
    currency: str
    settlement_account_number: Optional[str] = None
    status: str
    configuration: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class InstitutionProcessingSystemCreate(BaseModel):
    institution_id: Optional[str] = None
    processing_system_id: str
    member_id: str
    acquirer_id: Optional[str] = None
    network_identifier: Optional[str] = None
    issuer_enabled: bool = True
    acquirer_enabled: bool = True
    message_format: str = "TIC_V2164E"
    routing_configuration: Dict[str, Any] = Field(default_factory=dict)
    status: str = "ACTIVE"


class InstitutionProcessingSystemOut(BaseModel):
    id: str
    institution_id: str
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
    processing_system_id: str
    ps_code: Optional[str] = None
    ps_name: Optional[str] = None
    member_id: str
    acquirer_id: Optional[str] = None
    network_identifier: Optional[str] = None
    issuer_enabled: bool
    acquirer_enabled: bool
    message_format: str
    routing_configuration: Dict[str, Any]
    status: str
    effective_from: datetime
    effective_to: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class BinRangeCreate(BaseModel):
    bin_prefix: str = Field(..., min_length=6, max_length=12, description="6 to 12 digit BIN prefix")
    bin_low: Optional[str] = None
    bin_high: Optional[str] = None
    pan_length: int = 16
    institution_id: str
    processing_system_id: Optional[str] = None
    card_type: str = "DEBIT"
    card_product: str = "VISA_DEBIT_CLASSIC"
    scheme: str = "ITCL"
    country_code: str = "050"
    currency: str = "BDT"
    is_on_us: bool = True
    status: str = "ACTIVE"


class BinRangeUpdate(BaseModel):
    bin_prefix: Optional[str] = None
    bin_low: Optional[str] = None
    bin_high: Optional[str] = None
    pan_length: Optional[int] = None
    institution_id: Optional[str] = None
    processing_system_id: Optional[str] = None
    card_type: Optional[str] = None
    card_product: Optional[str] = None
    scheme: Optional[str] = None
    country_code: Optional[str] = None
    currency: Optional[str] = None
    is_on_us: Optional[bool] = None
    status: Optional[str] = None


class BinRangeOut(BaseModel):
    id: str
    bin_prefix: str
    bin_low: str
    bin_high: str
    pan_length: int
    institution_id: str
    institution_code: Optional[str] = None
    institution_name: Optional[str] = None
    processing_system_id: str
    ps_code: Optional[str] = None
    ps_name: Optional[str] = None
    card_type: str
    card_product: str
    scheme: str
    country_code: str
    currency: str
    is_on_us: bool
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
'''

SEED_ADDITION = '''

def seed_processing_systems_and_institutions(db: Session) -> None:
    """
    Idempotently seeds:
      1. Processing Systems: ITCL (default), VISA, MASTERCARD, NPSB, INTERNAL
      2. Initial Banks (all assigned to ITCL): xBank, yBank, zBank
      3. Institution-to-Processing-System participation records (all initial banks -> ITCL)
      4. Sample BIN Ranges mapped to xBank, yBank, zBank under ITCL
    Safe to run on every startup, including existing databases.
    """
    from app.models import (
        BinRange,
        Institution,
        InstitutionProcessingSystem,
        ProcessingSystem,
    )

    ps_definitions = [
        (
            "ITCL",
            "Information Technology Consultants Ltd (QCash Host Switch)",
            "HOST_SWITCH",
            "TIC_V2164E",
            True,
            True,
            {
                "protocol": "Compass Plus TW TIC/TCI v2.164e",
                "country": "BD",
                "default_currency": "BDT",
                "header_h1": "A4M",
                "settlement_cutover": "23:59",
            },
        ),
        (
            "VISA",
            "VisaNet / Visa Clearing Exchange (VCX)",
            "CARD_SCHEME",
            "ISO8583_1987",
            True,
            False,
            {
                "protocol": "ISO 8583:1987 VIP",
                "default_currency": "USD",
                "network_id": "0002",
            },
        ),
        (
            "MASTERCARD",
            "Mastercard Banknet / MDS",
            "CARD_SCHEME",
            "ISO8583_1987",
            True,
            False,
            {
                "protocol": "ISO 8583:1987 CIS/MDS",
                "default_currency": "USD",
                "network_id": "0003",
            },
        ),
        (
            "NPSB",
            "National Payment Switch Bangladesh (Bangladesh Bank)",
            "NATIONAL_SWITCH",
            "ISO8583_1987",
            True,
            False,
            {
                "protocol": "ISO 8583:1987 NPSB",
                "country": "BD",
                "default_currency": "BDT",
                "network_id": "0050",
            },
        ),
        (
            "INTERNAL",
            "BAOBAB Internal Host Loopback",
            "INTERNAL",
            "TIC_V2164E",
            True,
            False,
            {
                "protocol": "INTERNAL_LOOPBACK",
                "default_currency": "BDT",
            },
        ),
    ]

    ps_map = {}
    for code, name, stype, fmt, enabled, is_def, cfg in ps_definitions:
        existing_ps = db.query(ProcessingSystem).filter(ProcessingSystem.ps_code == code).first()
        if not existing_ps:
            existing_ps = ProcessingSystem(
                ps_code=code,
                name=name,
                system_type=stype,
                message_format=fmt,
                enabled=enabled,
                is_default=is_def,
                configuration=cfg,
            )
            db.add(existing_ps)
            db.flush()
        ps_map[code] = existing_ps

    itcl_ps = ps_map["ITCL"]

    # Seed initial banks (xBank, yBank, zBank) — all strictly assigned to ITCL
    bank_definitions = [
        ("XBANK", "xBank PLC", "xBank", "123456", "123456", "BOTH", "SETL-XBANK-001"),
        ("YBANK", "yBank Limited", "yBank", "223456", "223456", "BOTH", "SETL-YBANK-002"),
        ("ZBANK", "zBank Commercial PLC", "zBank", "323456", "323456", "BOTH", "SETL-ZBANK-003"),
    ]

    inst_map = {}
    for icode, iname, short, acq_id, fwd_id, role, setl_acct in bank_definitions:
        inst = db.query(Institution).filter(Institution.institution_code == icode).first()
        if not inst:
            inst = Institution(
                institution_code=icode,
                name=iname,
                short_name=short,
                acquirer_id=acq_id,
                forwarding_id=fwd_id,
                role=role,
                processing_system_id=itcl_ps.id,
                country_code="050",
                currency="BDT",
                settlement_account_number=setl_acct,
                status="ACTIVE",
                configuration={"on_us_host": "ITCL", "stand_in_enabled": True},
            )
            db.add(inst)
            db.flush()
        inst_map[icode] = inst

        # Ensure primary ITCL participation link exists in institution_processing_systems
        link = (
            db.query(InstitutionProcessingSystem)
            .filter(
                InstitutionProcessingSystem.institution_id == inst.id,
                InstitutionProcessingSystem.processing_system_id == itcl_ps.id,
            )
            .first()
        )
        if not link:
            db.add(
                InstitutionProcessingSystem(
                    institution_id=inst.id,
                    processing_system_id=itcl_ps.id,
                    member_id=f"ITCL-{icode}",
                    acquirer_id=acq_id,
                    network_identifier="ITCL_QCSH",
                    issuer_enabled=True,
                    acquirer_enabled=True,
                    message_format="TIC_V2164E",
                    routing_configuration={"priority": 1, "is_primary_host": True},
                    status="ACTIVE",
                )
            )
            db.flush()

    # Seed sample BIN ranges under ITCL
    # Note: 456789 matches existing seeded cards (4567890123450001..0005)
    bin_definitions = [
        ("456789", "4567890000000000", "4567899999999999", 16, "XBANK", "DEBIT", "VISA_DEBIT_CLASSIC", "ITCL", True),
        ("456790", "4567900000000000", "4567909999999999", 16, "XBANK", "CREDIT", "VISA_GOLD_CREDIT", "ITCL", True),
        ("512345", "5123450000000000", "5123459999999999", 16, "YBANK", "DEBIT", "MC_DEBIT_STANDARD", "ITCL", True),
        ("489012", "4890120000000000", "4890129999999999", 16, "ZBANK", "DEBIT", "QCASH_PROPRIETARY_DEBIT", "ITCL", True),
    ]

    for prefix, low, high, plen, icode, ctype, prod, scheme, on_us in bin_definitions:
        existing_bin = db.query(BinRange).filter(BinRange.bin_prefix == prefix).first()
        if not existing_bin and icode in inst_map:
            db.add(
                BinRange(
                    bin_prefix=prefix,
                    bin_low=low,
                    bin_high=high,
                    pan_length=plen,
                    institution_id=inst_map[icode].id,
                    processing_system_id=itcl_ps.id,
                    card_type=ctype,
                    card_product=prod,
                    scheme=scheme,
                    country_code="050",
                    currency="BDT",
                    is_on_us=on_us,
                    status="ACTIVE",
                )
            )

    db.commit()
'''


def main() -> int:
    args = parse_installer_args("Step 01_01: Models, Schemas & Seeding for Processing Systems, Institutions & BINs")
    session = PatcherSession(
        step_id="step01_01",
        title="Add ProcessingSystem, Institution, InstitutionProcessingSystem & BinRange Models, Schemas, and Seeding",
        dry_run=args.dry_run,
    )

    # 1. Patch backend/app/models.py to append Step 1 models
    session.patch_file(
        "backend/app/models.py",
        [
            {
                "marker": "step01_01:institution_and_ps_models",
                "action": "append",
                "text": MODELS_ADDITION.lstrip("\n"),
            }
        ],
    )

    # 2. Patch backend/app/schemas.py to append Step 1 schemas
    session.patch_file(
        "backend/app/schemas.py",
        [
            {
                "marker": "step01_01:institution_and_ps_schemas",
                "action": "append",
                "text": SCHEMAS_ADDITION.lstrip("\n"),
            }
        ],
    )

    # 3. Patch backend/app/seed_data.py so seed_processing_systems_and_institutions runs idempotently
    session.patch_file(
        "backend/app/seed_data.py",
        [
            {
                "marker": "step01_01:seed_early_call",
                "action": "replace",
                "anchor": (
                    "def seed_initial_data(db: Session) -> None:\n"
                    "    if db.query(Customer).count() > 0:\n"
                    "        return"
                ),
                "text": (
                    "def seed_initial_data(db: Session) -> None:\n"
                    "    seed_processing_systems_and_institutions(db)\n"
                    "    if db.query(Customer).count() > 0:\n"
                    "        return"
                ),
            },
            {
                "marker": "step01_01:seed_ps_and_institutions_fn",
                "action": "append",
                "text": SEED_ADDITION.lstrip("\n"),
            },
        ],
    )

    session.record_progress(
        completed=[
            "Added `ProcessingSystem`, `Institution`, `InstitutionProcessingSystem`, and `BinRange` ORM models to `backend/app/models.py`.",
            "Added Pydantic v2 schemas (`ProcessingSystemCreate/Update/Out`, `InstitutionCreate/Update/Out`, `InstitutionProcessingSystemCreate/Out`, `BinRangeCreate/Update/Out`) to `backend/app/schemas.py`.",
            "Added idempotent `seed_processing_systems_and_institutions(db)` in `backend/app/seed_data.py` seeding `ITCL`, `VISA`, `MASTERCARD`, `NPSB`, `INTERNAL`, banks `xBank`, `yBank`, `zBank` (all under `ITCL`), and 4 BIN ranges.",
        ],
        remaining=[
            "Step 1 Script 2 of 3 (`tools/install_step01_02.py`): Create `backend/app/routers/institutions_router.py`, wire into `main.py`, and add pytest test suite.",
            "Step 1 Script 3 of 3 (`tools/install_step01_03.py`): Create React UI page `InstitutionsAndBinsPage.tsx` and wire navigation in `App.tsx` and `Layout.tsx`.",
        ],
        modified_files=[
            "backend/app/models.py",
            "backend/app/schemas.py",
            "backend/app/seed_data.py",
        ],
    )

    session.record_contracts(
        section_title="Step 1.1 — Processing Systems, Institutions & BIN Ranges (Database & Schemas)",
        contract_items=[
            "**Table `processing_systems`**: `id`, `ps_code` (`ITCL`, `VISA`, `MASTERCARD`, `NPSB`, `INTERNAL`), `name`, `system_type`, `message_format`, `enabled`, `is_default`, `configuration`, `created_at`, `updated_at`.",
            "**Table `institutions`**: `id`, `institution_code` (`XBANK`, `YBANK`, `ZBANK`, `IFIC`, ...), `name`, `short_name`, `acquirer_id` (`DE32`), `forwarding_id` (`DE33`), `role` (`ISSUER`/`ACQUIRER`/`BOTH`), `processing_system_id` (FK -> `ITCL` by default), `country_code`, `currency`, `settlement_account_number`, `status`, `configuration`, `created_at`, `updated_at`.",
            "**Table `institution_processing_systems`**: `id`, `institution_id`, `processing_system_id`, `member_id`, `acquirer_id`, `network_identifier`, `issuer_enabled`, `acquirer_enabled`, `message_format`, `routing_configuration`, `status`, `effective_from`, `effective_to`, `created_at`, `updated_at`.",
            "**Table `bin_ranges`**: `id`, `bin_prefix`, `bin_low`, `bin_high`, `pan_length`, `institution_id`, `processing_system_id`, `card_type`, `card_product`, `scheme`, `country_code`, `currency`, `is_on_us`, `status`, `created_at`, `updated_at`.",
        ],
    )

    return session.finish()


if __name__ == "__main__":
    sys.exit(main())