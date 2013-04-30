package de.entropia.vapor.server

import de.entropia.vapor.mixer.{Overlay, Mixer}
import de.entropia.vapor.util.Color
import grizzled.slf4j.Logging
import de.entropia.vapor.daemon.config.{Settings, Token}
import de.entropia.vapor.daemon.config.Token.Seq2TokenId
import de.entropia.vapor.daemon.mixer.Manager


class Client(val settings: Settings, val mixer: Mixer, val manager: Manager) extends Logging {
  var token: Option[Token] = None
  var overlay: Option[Overlay] = None

  def dispatch(message: Message) = message match {
    case AuthMessage(bytes) => auth(bytes)
    case SetMessage(led, color) => setLed(led, color)
    case StrobeMessage() => strobe()
  }

  def auth(bytes: Seq[Byte]) {
    overlay.map(_.free())
    token = settings.tokens.get(bytes)
    token match {
      case None =>
        overlay = None
      case Some(t: Token) =>
        overlay = Some(manager.getOverlay(t))
    }
  }

  def setLed(i: Int, color: Color) {
    overlay match {
      case Some(o: Overlay) =>
        o.set(i, color)
      case None =>
    }
  }

  def strobe() {
    overlay match {
      case Some(o: Overlay) =>
        o.strobe()
      case None =>
    }
  }

  def connect() {
  }

  def disconnect() {
    overlay.map(_.free())
  }
}