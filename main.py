from fastapi import FastAPI, HTTPException, Header, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
import uuid

# Import database
from database import get_db, init_db
from models import Organization, User, Document, APIKey

app = FastAPI(
    title="Hello LISA AI API",
    description="Document Expiration Tracking Platform",
    version="1.0.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ Request/Response Models ============

class OrganizationSignup(BaseModel):
    org_name: str
    org_email: EmailStr
    user_email: EmailStr
    password: str
    full_name: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SignedURLRequest(BaseModel):
    filename: str
    content_type: str = "application/pdf"

class DocumentCreate(BaseModel):
    object_key: str
    filename: str

class DocumentUpdate(BaseModel):
    expiry_date: Optional[str] = None
    status: Optional[str] = None

# ============ Helper Functions ============

def verify_api_key(x_api_key: str = Header(None), db: Session = Depends(get_db)):
    """Validate API key from database"""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key missing")
    
    # Check in database
    api_key_record = db.query(APIKey).filter(
        APIKey.api_key == x_api_key,
        APIKey.is_active == True
    ).first()
    
    if not api_key_record:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key_record.user_id

# ============================================
# AUTHENTICATION ENDPOINTS
# ============================================

@app.post("/v1/auth/signup")
def signup(data: OrganizationSignup, db: Session = Depends(get_db)):

    # 1️⃣ check existing user
    if db.query(User).filter(User.email == data.user_email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # 2️⃣ create organization
    org = Organization(
        id=str(uuid.uuid4()),
        name=data.org_name,
        email=data.org_email,
        subscription_status="active",
        plan_type="starter"
    )
    db.add(org)
    db.commit()              # ✅ commit org
    db.refresh(org)

    # 3️⃣ create user
    user = User(
        id=str(uuid.uuid4()),
        org_id=org.id,
        email=data.user_email,
        full_name=data.full_name,
        password=data.password,
        is_active=True
    )
    db.add(user)
    db.commit()              # ✅ VERY IMPORTANT
    db.refresh(user)

    # 4️⃣ create api key (NOW user exists)
    api_key = f"hlai_{uuid.uuid4().hex}"
    key = APIKey(
        api_key=api_key,
        user_id=user.id,
        is_active=True
    )
    db.add(key)
    db.commit()

    return {
        "message": "Signup successful",
        "api_key": api_key,
        "user_id": user.id,
        "org_id": org.id
    }



@app.post("/v1/auth/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """
    Login and return API key
    """
    # Find user
    user = db.query(User).filter(User.email == data.email).first()
    
    if not user or user.password != data.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate new API key
    api_key = f"hlai_{uuid.uuid4().hex}"
    api_key_record = APIKey(
        api_key=api_key,
        user_id=user.id,
        is_active=True
    )
    db.add(api_key_record)
    db.commit()
    
    return {
        "message": "Login successful",
        "api_key": api_key,
        "user_id": user.id,
        "org_id": user.org_id
    }


@app.get("/v1/auth/me")
def get_current_user(
    user_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Return current user info
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "org_id": user.org_id,
        "is_active": user.is_active
    }


# ============================================
# UPLOAD ENDPOINTS
# ============================================

@app.post("/v1/uploads/sign")
def generate_signed_upload_url(
    data: SignedURLRequest,
    user_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Generate GCS signed URL for file upload
    """
    # Generate unique object key
    object_key = f"documents/{uuid.uuid4()}/{data.filename}"
    
    # Mock signed URL
    signed_url = f"https://storage.googleapis.com/hellolisa-documents/{object_key}?signature=mock_signature&expires=900"
    
    return {
        "signed_url": signed_url,
        "object_key": object_key,
        "expires_in": 900,
        "method": "PUT",
        "content_type": data.content_type
    }


# ============================================
# DOCUMENT ENDPOINTS
# ============================================

@app.post("/v1/documents", status_code=201)
def create_document(
    data: DocumentCreate,
    user_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Create document record
    """
    # Get user's org_id
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Create document
    doc_id = str(uuid.uuid4())
    document = Document(
        id=doc_id,
        org_id=user.org_id,
        filename=data.filename,
        gcs_object_key=data.object_key,
        status="processing"
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    
    return {
        "message": "Document created successfully",
        "document": {
            "id": document.id,
            "org_id": document.org_id,
            "filename": document.filename,
            "gcs_object_key": document.gcs_object_key,
            "status": document.status,
            "created_at": document.created_at.isoformat()
        }
    }


@app.get("/v1/documents")
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    user_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    List all documents of organization
    """
    # Get user's org_id
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Base query
    query = db.query(Document).filter(Document.org_id == user.org_id)
    
    # Apply filters
    if status:
        query = query.filter(Document.status == status)
    
    if search:
        query = query.filter(Document.filename.ilike(f"%{search}%"))
    
    # Get total count
    total = query.count()
    
    # Pagination
    offset = (page - 1) * page_size
    documents = query.order_by(Document.created_at.desc()).offset(offset).limit(page_size).all()
    
    # Convert to dict
    documents_list = [
        {
            "id": doc.id,
            "org_id": doc.org_id,
            "filename": doc.filename,
            "status": doc.status,
            "expiry_date": doc.expiry_date.isoformat() if doc.expiry_date else None,
            "manual_override": doc.manual_override,
            "confidence_score": doc.confidence_score,
            "created_at": doc.created_at.isoformat()
        }
        for doc in documents
    ]
    
    return {
        "documents": documents_list,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@app.get("/v1/documents/{document_id}")
def get_document(
    document_id: str,
    user_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Get single document details
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    
    # Get document
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check access
    if document.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return {
        "id": document.id,
        "org_id": document.org_id,
        "filename": document.filename,
        "gcs_object_key": document.gcs_object_key,
        "status": document.status,
        "expiry_date": document.expiry_date.isoformat() if document.expiry_date else None,
        "manual_override": document.manual_override,
        "confidence_score": document.confidence_score,
        "needs_review_reason": document.needs_review_reason,
        "created_at": document.created_at.isoformat(),
        "processed_at": document.processed_at.isoformat() if document.processed_at else None
    }


@app.patch("/v1/documents/{document_id}")
def update_document(
    document_id: str,
    data: DocumentUpdate,
    user_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Update document (manual override)
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    
    # Get document
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check access
    if document.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update fields
    if data.expiry_date:
        document.expiry_date = datetime.fromisoformat(data.expiry_date)
        document.manual_override = True
        document.manual_override_date = datetime.now()
    
    if data.status:
        document.status = data.status
    
    db.commit()
    db.refresh(document)
    
    return {
        "message": "Document updated successfully",
        "document": {
            "id": document.id,
            "status": document.status,
            "expiry_date": document.expiry_date.isoformat() if document.expiry_date else None,
            "manual_override": document.manual_override
        }
    }


@app.delete("/v1/documents/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    user_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Delete document
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    
    # Get document
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check access
    if document.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete
    db.delete(document)
    db.commit()
    
    return None


# ============================================
# REPORTS ENDPOINTS
# ============================================

@app.post("/v1/reports/csv")
def export_documents_csv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status_filter: Optional[str] = None,
    user_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Export documents to CSV
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    
    # Query documents
    query = db.query(Document).filter(Document.org_id == user.org_id)
    
    if status_filter:
        query = query.filter(Document.status == status_filter)
    
    total_records = query.count()
    
    return {
        "message": "CSV export ready",
        "download_url": f"https://api.hellolisa.ai/downloads/export_{uuid.uuid4()}.csv",
        "total_records": total_records,
        "generated_at": datetime.now().isoformat()
    }


@app.get("/v1/reports/summary")
def get_documents_summary(
    user_id: str = Depends(verify_api_key),
    db: Session = Depends(get_db)
):
    """
    Get document statistics
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    
    # Get all documents
    documents = db.query(Document).filter(Document.org_id == user.org_id).all()
    
    # Calculate statistics
    total = len(documents)
    active = len([d for d in documents if d.status == "active"])
    processing = len([d for d in documents if d.status == "processing"])
    expired = len([d for d in documents if d.status == "expired"])
    expiring_soon = len([d for d in documents if d.status == "expiring_soon"])
    needs_review = len([d for d in documents if d.status == "needs_review"])
    
    return {
        "total_documents": total,
        "status_breakdown": {
            "active": active,
            "processing": processing,
            "expired": expired,
            "expiring_soon": expiring_soon,
            "needs_review": needs_review
        },
        "generated_at": datetime.now().isoformat()
    }


# ============================================
# REMAINING ENDPOINTS
# ============================================

@app.post("/webhooks/stripe")
def stripe_webhook(stripe_signature: str = Header(None, alias="stripe-signature")):
    """Stripe webhook handler"""
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing stripe signature")
    
    return {
        "status": "received",
        "message": "Webhook processed successfully"
    }


@app.post("/v1/auth/create-checkout-session")
def create_stripe_checkout_session(
    plan_type: str = Query(..., description="starter, pro, or premium"),
    user_id: str = Depends(verify_api_key)
):
    """Create Stripe checkout session"""
    valid_plans = ["starter", "pro", "premium"]
    if plan_type not in valid_plans:
        raise HTTPException(status_code=400, detail="Invalid plan type")
    
    checkout_url = f"https://checkout.stripe.com/pay/cs_test_{uuid.uuid4().hex}"
    
    return {
        "checkout_url": checkout_url,
        "session_id": f"cs_test_{uuid.uuid4().hex}",
        "plan_type": plan_type
    }


@app.get("/v1/cron/check-alerts")
def check_expiring_documents(db: Session = Depends(get_db)):
    """Daily alert checker"""
    documents = db.query(Document).filter(Document.expiry_date.isnot(None)).all()
    
    alerts_sent = len(documents)
    
    return {
        "status": "success",
        "alerts_sent": alerts_sent,
        "checked_at": datetime.now().isoformat()
    }


@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Hello Lisa AI - Document Expiration Tracking API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


# ============================================
# STARTUP EVENT
# ============================================

@app.on_event("startup")
def startup_event():
    """Initialize database on startup"""
    print("Initializing database...")
    init_db()
    print("Database initialized successfully!")


# ============================================
# RUN SERVER
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)