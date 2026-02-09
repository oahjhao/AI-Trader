# GitHub Actions Setup for AI-Trader

This guide explains how to set up GitHub Actions for building and pushing Docker images to AWS ECR.

## Prerequisites

### 1. AWS Configuration

#### IAM Role for GitHub OIDC
Create an IAM role for GitHub Actions with OIDC federation:

1. Go to AWS IAM Console
2. Create a new role with the following trust relationship:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::992382447135:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:oahjhao/AI-Trader:*"
        }
      }
    }
  ]
}
```

3. Attach the following policies to the role:
   - `AmazonEC2ContainerRegistryPowerUser` (for ECR push/pull)
   - `AmazonECS_FullAccess` (if you plan to update ECS tasks)

#### ECR Repositories
Create two ECR repositories in `us-west-2` region:
1. `shanavasa/trader-app`
2. `shanavasa/trader-frontend`

### 2. GitHub Repository Secrets

Add the following secrets to your GitHub repository (Settings → Secrets and variables → Actions):

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `AWS_ROLE_ARN` | `arn:aws:iam::992382447135:role/GitHubActionsOIDCRole` | IAM Role ARN for OIDC |
| `AWS_REGION` | `us-west-2` | AWS Region |
| `DINGTALK_WEBHOOK_URL` | `https://oapi.dingtalk.com/robot/send?access_token=0e2effcc1d395b7c7720101fd66dc6296ff51cc0aaea952661f2a5f8164938c8` | DingTalk webhook URL |

## Workflow Overview

The GitHub Actions workflow (`build-and-push-ecr.yml`) does the following:

1. **Triggers**: On push to `hexiu/dev_reconstruction` or `main` branches, or manual dispatch
2. **AWS Authentication**: Uses OIDC to assume IAM role
3. **ECR Login**: Authenticates with Amazon ECR
4. **Build Images**: Builds both Docker images with Buildx caching
5. **Push to ECR**: Pushes images with `latest` and commit SHA tags
6. **Notifications**: Sends DingTalk notifications on success/failure

## Local Testing

Before pushing to GitHub, test the Docker builds locally:

```bash
# Make the test script executable
chmod +x test-docker-build.sh

# Run the test
./test-docker-build.sh
```

## Manual Trigger

You can manually trigger the workflow from the GitHub Actions tab:
1. Go to "Actions" in your repository
2. Select "Build and Push to ECR" workflow
3. Click "Run workflow"
4. Select branch and click "Run workflow"

## Image Tags

The workflow creates the following image tags:

### For `trader-app`:
- `992382447135.dkr.ecr.us-west-2.amazonaws.com/shanavasa/trader-app:latest`
- `992382447135.dkr.ecr.us-west-2.amazonaws.com/shanavasa/trader-app:<commit-sha>`

### For `trader-frontend`:
- `992382447135.dkr.ecr.us-west-2.amazonaws.com/shanavasa/trader-frontend:latest`
- `992382447135.dkr.ecr.us-west-2.amazonaws.com/shanavasa/trader-frontend:<commit-sha>`

## Troubleshooting

### Common Issues

1. **Permission denied when pushing to ECR**
   - Verify the IAM role has `AmazonEC2ContainerRegistryPowerUser` policy
   - Check that the OIDC trust relationship is correctly configured

2. **Docker build fails**
   - Check Dockerfile syntax
   - Verify all required files exist in the repository
   - Test locally with `./test-docker-build.sh`

3. **DingTalk notifications not working**
   - Verify the webhook URL is correct
   - Check DingTalk robot configuration

### Logs
- GitHub Actions logs: Repository → Actions → Select workflow run → View logs
- ECR logs: AWS Console → ECR → Repository → View push history

## Next Steps

After successful image builds:

1. **Update ECS Task Definitions** to use the new images
2. **Deploy to ECS** using the updated task definitions
3. **Monitor** the deployment in AWS ECS console

## References

- [GitHub Actions OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [AWS ECR GitHub Action](https://github.com/aws-actions/amazon-ecr-login)
- [Docker Build Push Action](https://github.com/docker/build-push-action)