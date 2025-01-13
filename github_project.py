import os
from typing import List, Dict, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

load_dotenv()

@dataclass
class GitHubIssue:
    title: str
    body: str
    labels: List[str]

@dataclass
class SelectOption:
    name: str
    color: str = "GRAY"  # Default color
    description: str = ""  # Default empty description

@dataclass
class ProjectField:
    name: str
    data_type: str
    options: Optional[List[SelectOption]] = None

class GitHubProjectManager:
    def __init__(self):
        self.token = os.getenv('GITHUB_TOKEN')
        if not self.token:
            raise ValueError("GITHUB_TOKEN environment variable is required")
        
        # Set up GQL client
        transport = RequestsHTTPTransport(
            url='https://api.github.com/graphql',
            headers={'Authorization': f'Bearer {self.token}'},
            verify=True,
            retries=3,
        )
        self.client = Client(transport=transport, fetch_schema_from_transport=True)

    def create_project(self, org_id: str, title: str) -> Dict:
        """Create a new project"""
        mutation = gql("""
        mutation($input: CreateProjectV2Input!) {
            createProjectV2(input: $input) {
                projectV2 {
                    id
                    number
                }
            }
        }
        """)
        
        variables = {
            'input': {
                'title': title,
                'repositoryId': os.getenv('GITHUB_REPO_ID')
            }
        }
        
        result = self.client.execute(mutation, variable_values=variables)
        return result

    def create_project_field(self, project_id: str, field: ProjectField) -> Dict:
        """Create a custom field in the project"""
        create_field_mutation = gql("""
        mutation($input: CreateProjectV2FieldInput!) {
            createProjectV2Field(input: $input) {
                projectV2Field {
                    ... on ProjectV2SingleSelectField {
                        id
                        name
                        options {
                            id
                            name
                        }
                    }
                }
            }
        }
        """)
        
        variables = {
            'input': {
                'projectId': project_id,
                'dataType': field.data_type,
                'name': field.name,
                'singleSelectOptions': [{'name': opt.name, 'color': opt.color, 'description': opt.description} for opt in (field.options or [])]
            }
        }
        
        result = self.client.execute(create_field_mutation, variable_values=variables)
        return result

    def update_single_select_options(self, field_id: str, options: List[str]) -> Dict:
        """Update the options for a single select field"""
        mutation = gql("""
        mutation($input: UpdateProjectV2FieldInput!) {
            updateProjectV2Field(input: $input) {
                projectV2Field {
                    ... on ProjectV2SingleSelectField {
                        id
                        options {
                            id
                            name
                        }
                    }
                }
            }
        }
        """)
        
        variables = {
            'input': {
                'fieldId': field_id,
                'singleSelectOptions': [{'name': opt} for opt in options]
            }
        }
        
        return self.client.execute(mutation, variable_values=variables)

    def create_issue(self, repo_id: str, issue: GitHubIssue) -> Dict:
        """Create a new issue"""
        mutation = gql("""
        mutation($input: CreateIssueInput!) {
            createIssue(input: $input) {
                issue {
                    id
                }
            }
        }
        """)
        
        variables = {
            'input': {
                'repositoryId': repo_id,
                'title': issue.title,
                'body': issue.body,
                'labelIds': issue.labels
            }
        }
        
        return self.client.execute(mutation, variable_values=variables)

    def add_issue_to_project(self, project_id: str, issue_id: str) -> Dict:
        """Add an issue to a project"""
        mutation = gql("""
        mutation($input: AddProjectV2ItemByIdInput!) {
            addProjectV2ItemById(input: $input) {
                item {
                    id
                }
            }
        }
        """)
        
        variables = {
            'input': {
                'projectId': project_id,
                'contentId': issue_id
            }
        }
        
        return self.client.execute(mutation, variable_values=variables)

    def update_item_field(self, project_id: str, item_id: str, field_id: str, value: Dict) -> Dict:
        """Update a field value for a project item"""
        mutation = gql("""
        mutation($input: UpdateProjectV2ItemFieldValueInput!) {
            updateProjectV2ItemFieldValue(input: $input) {
                projectV2Item {
                    id
                }
            }
        }
        """)
        
        variables = {
            'input': {
                'projectId': project_id,
                'itemId': item_id,
                'fieldId': field_id,
                'value': value
            }
        }
        
        return self.client.execute(mutation, variable_values=variables)

    def get_projects(self, org_id: str) -> Dict:
        """Get all projects for a user"""
        query = gql("""
        query {
            viewer {
                projectsV2(first: 20) {
                    nodes {
                        id
                        title
                    }
                }
            }
        }
        """)
        
        return self.client.execute(query)

    def get_repository_issues(self, repo_id: str) -> Dict:
        """Get all issues in a repository"""
        query = gql("""
        query($repoId: ID!) {
            node(id: $repoId) {
                ... on Repository {
                    issues(first: 100, states: [OPEN]) {
                        nodes {
                            id
                            title
                        }
                    }
                }
            }
        }
        """)
        
        variables = {
            'repoId': repo_id
        }
        
        return self.client.execute(query, variable_values=variables)

    def create_label(self, repo_id: str, name: str, color: str, description: str = "") -> Dict:
        """Create a label in the repository"""
        mutation = gql("""
        mutation($input: CreateLabelInput!) {
            createLabel(input: $input) {
                label {
                    id
                }
            }
        }
        """)
        
        variables = {
            'input': {
                'repositoryId': repo_id,
                'name': name,
                'color': color,
                'description': description
            }
        }
        
        return self.client.execute(mutation, variable_values=variables)

    def create_milestone(self, repo_id: str, title: str, description: str, due_on: str) -> Dict:
        """Create a milestone in the repository"""
        mutation = gql("""
        mutation($input: CreateMilestoneInput!) {
            createMilestone(input: $input) {
                milestone {
                    id
                }
            }
        }
        """)
        
        variables = {
            'input': {
                'repositoryId': repo_id,
                'title': title,
                'description': description,
                'dueOn': due_on
            }
        }
        
        return self.client.execute(mutation, variable_values=variables)

    def create_priority_field(self, project_id: str) -> Dict:
        """Create a priority field in the project"""
        priority_field = ProjectField(
            name="Priority",
            data_type="SINGLE_SELECT",
            options=[
                SelectOption(name="High", color="RED"),
                SelectOption(name="Medium", color="YELLOW"),
                SelectOption(name="Low", color="GREEN")
            ]
        )
        return self.create_project_field(project_id, priority_field)

    def create_effort_field(self, project_id: str) -> Dict:
        """Create an effort estimation field in the project"""
        effort_field = ProjectField(
            name="Effort",
            data_type="NUMBER"
        )
        return self.create_project_field(project_id, effort_field)

    def create_target_date_field(self, project_id: str) -> Dict:
        """Create a target date field in the project"""
        date_field = ProjectField(
            name="Target Date",
            data_type="DATE"
        )
        return self.create_project_field(project_id, date_field)

    def delete_project(self, project_id: str) -> Dict:
        """Delete a project"""
        mutation = gql("""
        mutation($input: DeleteProjectV2Input!) {
            deleteProjectV2(input: $input) {
                projectV2 {
                    id
                }
            }
        }
        """)
        
        variables = {
            'input': {
                'projectId': project_id
            }
        }
        
        return self.client.execute(mutation, variable_values=variables)

    def get_project_fields(self, project_id: str) -> Dict:
        """Get all fields in a project"""
        query = gql("""
        query($projectId: ID!) {
            node(id: $projectId) {
                ... on ProjectV2 {
                    fields(first: 20) {
                        nodes {
                            ... on ProjectV2Field {
                                id
                                name
                            }
                            ... on ProjectV2SingleSelectField {
                                id
                                name
                                options {
                                    id
                                    name
                                }
                            }
                        }
                    }
                }
            }
        }
        """)
        
        variables = {
            'projectId': project_id
        }
        
        return self.client.execute(query, variable_values=variables)

def create_monorepo_project():
    """Create the monorepo infrastructure project with all tasks"""
    manager = GitHubProjectManager()
    project_title = "Monorepo Infrastructure Setup"
    
    try:
        # Check if project already exists
        projects = manager.get_projects(None)
        print(f"Projects response: {projects}")
        existing_projects = [p for p in projects['viewer']['projectsV2']['nodes'] if p['title'] == project_title]
        
        # If multiple projects exist, keep the first one and delete the rest
        if len(existing_projects) > 1:
            print(f"Found {len(existing_projects)} projects with title '{project_title}'. Cleaning up duplicates...")
            for project in existing_projects[1:]:
                manager.delete_project(project['id'])
                print(f"Deleted duplicate project with ID: {project['id']}")
            
            project_id = existing_projects[0]['id']
            print(f"Using project with ID: {project_id}")
        elif len(existing_projects) == 1:
            project_id = existing_projects[0]['id']
            print(f"Using existing project with ID: {project_id}")
        else:
            # Create new project
            project_result = manager.create_project(None, project_title)
            project_id = project_result['createProjectV2']['projectV2']['id']
            print(f"Created new project with ID: {project_id}")
            
            # Create custom fields
            manager.create_priority_field(project_id)
            print("Created priority field")
            
            manager.create_effort_field(project_id)
            print("Created effort field")
            
            manager.create_target_date_field(project_id)
            print("Created target date field")
            
            # Create Status field with colored options
            status_field = ProjectField(
                name="Task Status",
                data_type="SINGLE_SELECT",
                options=[
                    SelectOption(name="Backlog", color="RED"),
                    SelectOption(name="Ready for Development", color="YELLOW"),
                    SelectOption(name="In Progress", color="BLUE"),
                    SelectOption(name="Review/QA", color="PURPLE"),
                    SelectOption(name="Done", color="GREEN")
                ]
            )
            status_field_result = manager.create_project_field(project_id, status_field)
            print("Created status field")
            
            # Create labels
            labels = [
                ("infrastructure", "0366d6", "Infrastructure related changes"),
                ("configuration", "fbca04", "Configuration and setup tasks"),
                ("maintenance", "d4c5f9", "Maintenance and cleanup tasks"),
                ("high-priority", "b60205", "High priority tasks"),
                ("documentation", "0075ca", "Documentation updates")
            ]
            
            for name, color, description in labels:
                manager.create_label(os.getenv('GITHUB_REPO_ID'), name, color, description)
                print(f"Created label: {name}")
            
            # Create milestone
            manager.create_milestone(
                os.getenv('GITHUB_REPO_ID'),
                "Monorepo Migration",
                "Complete the migration to a proper monorepo structure",
                "2024-03-31T00:00:00Z"  # Set an appropriate due date
            )
            print("Created milestone")
        
        # Get field information for the workflow
        fields = manager.get_project_fields(project_id)
        print("\nField information for workflow configuration:")
        print(f"Fields response: {fields}")
        
        # Get existing issues
        issues_result = manager.get_repository_issues(os.getenv('GITHUB_REPO_ID'))
        existing_issues = issues_result['node']['issues']['nodes']
        
        # Create parent issue if it doesn't exist
        parent_title = "Railway Configuration Optimization"
        parent_issue = next((i for i in existing_issues if i['title'] == parent_title), None)
        
        if parent_issue:
            print(f"Parent issue already exists with ID: {parent_issue['id']}")
            parent_id = parent_issue['id']
        else:
            parent_issue_data = GitHubIssue(
                title=parent_title,
                body="Restructure and optimize Railway configuration for proper monorepo support",
                labels=["infrastructure", "high-priority"]
            )
            parent_result = manager.create_issue(os.getenv('GITHUB_REPO_ID'), parent_issue_data)
            parent_id = parent_result['createIssue']['issue']['id']
            print(f"Created parent issue with ID: {parent_id}")
            
            # Add parent issue to project
            manager.add_issue_to_project(project_id, parent_id)
            print("Added parent issue to project")
        
        # Create sub-tasks if they don't exist
        subtasks = [
            GitHubIssue(
                title="Directory Structure Cleanup",
                body="- Create `services` directory in root\n- Move FastAPI service to `services/fastapi`\n- Remove nested .git directory\n- Verify file paths after migration",
                labels=["maintenance", "infrastructure"]
            ),
            GitHubIssue(
                title="Railway Configuration Enhancement",
                body="- Create updated railway.json with proper schema\n- Configure root directory setting\n- Set up watch paths\n- Test build triggers",
                labels=["configuration", "high-priority"]
            ),
            GitHubIssue(
                title="Service Isolation Implementation",
                body="- Audit current dependencies\n- Move service-specific files\n- Update environment variable structure\n- Verify service isolation",
                labels=["infrastructure", "configuration"]
            ),
            GitHubIssue(
                title="Build and Deploy Pipeline",
                body="- Configure selective build triggers\n- Set up environment variables in Railway dashboard\n- Implement health checks\n- Test deployment pipeline",
                labels=["infrastructure", "documentation"]
            )
        ]
        
        for subtask in subtasks:
            existing_subtask = next((i for i in existing_issues if i['title'] == subtask.title), None)
            if existing_subtask:
                print(f"Subtask '{subtask.title}' already exists with ID: {existing_subtask['id']}")
                continue
                
            result = manager.create_issue(os.getenv('GITHUB_REPO_ID'), subtask)
            issue_id = result['createIssue']['issue']['id']
            manager.add_issue_to_project(project_id, issue_id)
            print(f"Created and added subtask: {subtask.title}")
            
    except Exception as e:
        print(f"Error: {str(e)}")
        raise

if __name__ == "__main__":
    create_monorepo_project() 