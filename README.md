# Job Auto Apply

100% free, AI-powered job application automation for college students. Scrapes jobs, customizes resumes, auto-applies, tracks, and follows up. Open-source, zero-cost stack.

## Overview

Job Auto Apply is an intelligent automation platform designed to streamline the job application process for college students. The system automatically:

- **Scrapes job listings** from multiple sources (LinkedIn, Indeed, etc.)
- **Customizes resumes and cover letters** for each application
- **Auto-applies** to matching positions
- **Tracks applications** and their status
- **Follows up** on pending applications

## Features

### 🔍 Job Scraping
- Automated daily scraping of job postings
- Support for multiple job boards (LinkedIn, Indeed, more coming)
- Intelligent filtering based on preferences
- MongoDB storage for efficient querying

### 🤖 AI-Powered Customization
- Resume tailoring for each job posting
- Custom cover letter generation
- Keyword optimization
- ATS-friendly formatting

### 📊 Application Tracking
- Comprehensive dashboard for all applications
- Status tracking (applied, pending, interview, rejected)
- Follow-up reminders
- Analytics and insights

### 🔐 Secure Authentication
- JWT-based authentication
- Secure password hashing with bcrypt
- User profile management

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **MongoDB** - NoSQL database for flexible data storage
- **PyJWT** - JWT authentication
- **BeautifulSoup4 & Selenium** - Web scraping
- **Passlib** - Password hashing

### Automation
- **GitHub Actions** - Scheduled job scraping
- **Uvicorn** - ASGI server

## Project Structure

```
job-auto-apply/
├── .github/
│   └── workflows/
│       └── scrape-jobs.yml    # Automated job scraping workflow
├── backend/
│   ├── api/
│   │   └── auth.py            # Authentication endpoints
│   ├── app/
│   │   └── scrapers/          # Job scraper modules
│   ├── db/
│   │   └── models.py          # MongoDB models and schemas
│   ├── requirements.txt       # Python dependencies
│   └── __init__.py
├── .gitignore
├── LICENSE
└── README.md
```

## Getting Started

### Prerequisites
- Python 3.10+
- MongoDB (local or Atlas)
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/nvarshi2004/job-auto-apply.git
cd job-auto-apply
```

2. Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your MongoDB URI and JWT secret
```

4. Run the server:
```bash
uvicorn app.main:app --reload
```

## API Endpoints

### Authentication
- `POST /signup` - Create new user account
- `POST /login` - Login and receive JWT token
- `GET /me` - Get current user information

### Jobs
- `GET /jobs` - List all scraped jobs
- `GET /jobs/{id}` - Get specific job details
- `POST /jobs/apply` - Apply to a job

### Applications
- `GET /applications` - List user's applications
- `GET /applications/{id}` - Get application details
- `PUT /applications/{id}` - Update application status

## Automated Job Scraping

The GitHub Actions workflow automatically scrapes job listings daily at 9 AM UTC. You can also trigger it manually:

1. Go to the Actions tab in your repository
2. Select "Scrape Jobs" workflow
3. Click "Run workflow"

## Environment Variables

Create a `.env` file in the backend directory:

```env
MONGODB_URI=mongodb://localhost:27017/
DATABASE_NAME=job_auto_apply
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Roadmap

- [ ] Frontend dashboard with React/Next.js
- [ ] AI resume customization with OpenAI API
- [ ] Email notification system
- [ ] More job board integrations (Glassdoor, Monster)
- [ ] Chrome extension for easy job saving
- [ ] Interview preparation assistant
- [ ] Salary negotiation insights

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by the challenges college students face in the job search process
- Built with modern, production-ready technologies
- 100% free and open-source

## Support

If you find this project helpful, please consider giving it a ⭐ on GitHub!

## Contact

For questions or suggestions, please open an issue on GitHub.

---

**Note**: This project is for educational purposes. Please respect websites' terms of service and robots.txt when scraping job listings.
