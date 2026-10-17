# DevOps Task Manager

A simple Kanban-style task board built with Flask and PostgreSQL. Tasks can be created, moved between **To Do**, **In Progress** and **Done**, and deleted.

The whole app runs inside Docker, so you do **not** need to install Python or PostgreSQL on your computer.

---

## Before you start

Make sure you have these installed:

- **Git**
- **Docker Desktop**: download it from <https://www.docker.com/products/docker-desktop/>

Open Docker Desktop and leave it running in the background. The steps below will not work unless Docker is running.

---

## Running the app locally

### 1. Get the code

If you haven't cloned the project yet, clone it first:

```bash
git clone https://github.com/Nisura-W/SWE40006-Group-Project.git
cd SWE40006-Group-Project
```

The application is available on `main`.

### 2. Start the app

From the project folder, run:

```bash
docker compose up --build
```

The first run takes a few minutes because Docker needs to download and build everything. Later runs are much faster.

The app is ready when you see a line like this in the terminal:

```text
[INFO] Booting worker with pid: ...
```

> **Mac users:** macOS uses port 5000 for AirPlay Receiver, so you may see a "403 Forbidden" page or a "port already in use" error. If that happens, stop the app with `Ctrl + C` and start it on port 5001 instead:
>
> ```bash
> WEB_PORT=5001 docker compose up --build
> ```

### 3. Open the task manager

Open your web browser and go to:

- **<http://localhost:5000>**
- or **<http://localhost:5001>** if you used the Mac workaround above.

You should see the task board with three columns. Try adding a task to check that everything works.

### 4. Run the tests (optional)

To check that the app works correctly on your machine, keep the app running and open a **second terminal window** in the project folder. Then run:

```bash
docker compose exec web pytest
```

All tests should show as passed.

### 5. Stop the app

When you are finished, go back to the first terminal and press **`Ctrl + C`**.

To fully shut down the containers, run:

```bash
docker compose down
```

Your tasks are saved, and they will still be there the next time you start the app.

If you want to **delete all saved tasks** and start with an empty board, run this instead:

```bash
docker compose down -v
```

---

## Troubleshooting

| Problem | What to do |
| --- | --- |
| `Cannot connect to the Docker daemon` | Docker Desktop isn't running. Open it, wait until it has started, then try again. |
| `port is already allocated` / `address already in use` | Something else is using that port. Start the app on another port, e.g. `WEB_PORT=5001 docker compose up --build`. |
| 403 Forbidden page on a Mac | This is AirPlay Receiver on port 5000. Use port 5001 as shown in step 2. |
| Changes to the code don't appear | Stop the app and start it again with `docker compose up --build` so it rebuilds. |

---

## Optional settings

You can change these values by putting them in front of the `docker compose` command (e.g. `BUILD_ID=v1.2 docker compose up --build`) or by adding them to a `.env` file in the project folder.

| Variable | What it does | Default |
| --- | --- | --- |
| `WEB_PORT` | Port the app opens on in your browser | `5000` |
| `BUILD_ID` | Build label shown in the page footer | `Local Dev` |
| `POSTGRES_USER` | Database username | `taskuser` |
| `POSTGRES_PASSWORD` | Database password | `taskpass` |
| `POSTGRES_DB` | Database name | `taskdb` |
| `SECRET_KEY` | Flask secret key | development placeholder |

The default values are for local development only. Use proper secrets in any real deployment.

## CI and release deployment

See [the release handoff](docs/release-handoff.md) for runner setup, secret names,
Person 4's test interfaces, local rollback checks and the commissioning checklist.
Release deployment is manual and disabled by default. The AWS Compose file pulls
an immutable `IMAGE_REF`; it no longer builds on the deployment server.
