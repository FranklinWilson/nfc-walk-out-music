from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import PasswordField, SelectField, StringField, SubmitField, TimeField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


class UploadForm(FlaskForm):
    mp3 = FileField(
        "MP3 file",
        validators=[FileRequired(), FileAllowed(["mp3"], "MP3 files only.")],
    )
    submit = SubmitField("Upload")


class AssignForm(FlaskForm):
    uid = StringField("Tag UID", validators=[DataRequired(), Length(max=64)])
    song = SelectField("Song", validators=[DataRequired()])
    label = StringField("Label (optional)", validators=[Length(max=64)])
    submit = SubmitField("Assign")


class PlaybackWindowForm(FlaskForm):
    start_time = TimeField("Allowed start time", validators=[DataRequired()])
    end_time = TimeField("Allowed end time", validators=[DataRequired()])
    submit = SubmitField("Save times")


class AudioOutputForm(FlaskForm):
    output = SelectField(
        "Speaker output",
        choices=[
            ("headphones", "Aux / headphone jack (wired speaker)"),
            ("hdmi", "HDMI"),
            ("auto", "Auto"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("Save output")


class CsrfOnlyForm(FlaskForm):
    """Used for simple POST actions (unassign/delete) that need only CSRF protection."""

